import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, String, Text, func
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
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

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
