import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class CommentStatus(str, enum.Enum):
    """Every comment lands in `pending` and is invisible until a moderator acts.

    Moderation-by-default is the design: the public read path only ever returns
    `approved`, so a compromised or abused posting path cannot publish anything.
    """

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Which page/thread the comment belongs to (e.g. a blog post slug).
    page_slug: Mapped[str] = mapped_column(String(200), index=True)

    # Identity from the verified JWT: the stable subject and a display name.
    author_sub: Mapped[str] = mapped_column(String(255), index=True)
    author_name: Mapped[str] = mapped_column(String(120))

    body: Mapped[str] = mapped_column(Text)

    status: Mapped[CommentStatus] = mapped_column(
        Enum(CommentStatus, name="comment_status"),
        default=CommentStatus.pending,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Recipe(Base):
    """Authored cooking content (from Steve's library classes).

    Unlike comments, recipes are authored, not user-generated: create/update
    requires the moderator role, and `published` gates public visibility (drafts
    stay private). `video_key` links to a lesson video transcoded by the media
    pipeline and served from CloudFront.
    """

    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    # The name of a Category (denormalized), or null for uncategorized. Validated
    # against the categories table at write time. Indexed for ?category= filters.
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # The name of a Cuisine (denormalized), validated against the cuisines table at
    # write time — a moderator-maintained vocabulary like category. Indexed for filters.
    cuisine: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # A hard-coded difficulty (Easy/Medium/Hard); validated in the schema, no table.
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A longer Markdown "story" (headnote, background, tips). Rendered to sanitized
    # HTML on the site; links in it (and in summary) are the hook for affiliate links.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # How many servings the ingredient quantities make. A structured field (not buried
    # in the summary) so the site can scale ingredients up/down. Always >= 1; recipes
    # with no known yield default to 1 (see migration 0008 and scripts/backfill_servings.py).
    servings: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Lists of strings, stored as JSON (JSONB on Postgres, text on SQLite).
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    steps: Mapped[list] = mapped_column(JSON, default=list)

    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Base key of a transcoded video (the site builds the HLS URL from the media
    # CloudFront domain + this key). Null until a lesson video is attached.
    video_key: Mapped[str | None] = mapped_column(String(300), nullable=True)

    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow
    )


class Category(Base):
    """The recipe category vocabulary — editable by moderators (add/rename/reorder/
    delete), so a new category is a data change, not a deploy. `Recipe.category`
    stores the name; renaming a category cascades to its recipes. `sort_order` drives
    display order on the site and in the admin list.
    """

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow
    )


class Cuisine(Base):
    """The recipe cuisine vocabulary — a moderator-maintained list exactly like
    Category (add/rename/reorder/delete). `Recipe.cuisine` stores the name; renaming
    cascades to its recipes. Kept separate from Category so a recipe can be both e.g.
    "Main Courses" (category) and "Spanish" (cuisine).
    """

    __tablename__ = "cuisines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow
    )


# --- Classes (cooking-class workshops) --------------------------------------
# Authored like recipes (moderator-gated, `published` gates visibility). A Class has
# 0+ scheduled ClassSessions people sign up for; a ClassRequest is interest in a class
# or a new date. No payment in this iteration — `price_cents`/signup `status` are
# reserved so a later payment layer needs no reshaping.


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)      # short, Markdown
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # long, Markdown
    # Products used in the class, each an Amazon affiliate link: [{name, url, note}].
    # Stored raw (untagged) — the site injects the Associates tag at render (md.js).
    tools: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow
    )


class ClassSession(Base):
    __tablename__ = "class_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null = unlimited
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled | cancelled
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # reserved for future payment
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow
    )


class ClassSignup(Base):
    __tablename__ = "class_signups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_sessions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # registered | waitlisted | cancelled (room for paid/pending once payment lands).
    status: Mapped[str] = mapped_column(String(20), default="registered")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class ClassRequest(Base):
    __tablename__ = "class_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The class this is about, or null for a general "teach a class" request.
    class_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("classes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_timeframe: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
