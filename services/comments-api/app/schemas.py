import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CommentStatus

# Hard-coded recipe difficulty levels (no table — a fixed vocabulary).
DIFFICULTIES = ("Easy", "Medium", "Hard")


class CommentCreate(BaseModel):
    page_slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9/_-]*$")
    body: str = Field(min_length=1, max_length=4000)


class CommentPublic(BaseModel):
    """What anonymous readers see — never the author's subject id."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_slug: str
    author_name: str
    body: str
    created_at: datetime


class CommentAdmin(CommentPublic):
    """What a moderator sees — includes status and the author subject."""

    author_sub: str
    status: CommentStatus
    moderated_at: datetime | None = None
    moderated_by: str | None = None


class ModerationAction(BaseModel):
    decision: CommentStatus = Field(description="approved or rejected")


# --- Categories ------------------------------------------------------------

# Categories are data (the `categories` table), managed by moderators. A recipe's
# category is optional (null) or the name of an existing category — enforced in the
# router against the DB, not statically here. The six seed names live in migration
# 0004.


class CategoryWrite(BaseModel):
    """Create/update payload for a category (moderator only)."""

    name: str = Field(min_length=1, max_length=50)
    sort_order: int = 0


class CategoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int


# --- Cuisines --------------------------------------------------------------

# Cuisines are data (the `cuisines` table), managed by moderators — same shape as
# categories. A recipe's cuisine is null or the name of an existing cuisine (enforced
# in the router against the DB). Seed set lives in migration 0006.


class CuisineWrite(BaseModel):
    """Create/update payload for a cuisine (moderator only)."""

    name: str = Field(min_length=1, max_length=50)
    sort_order: int = 0


class CuisinePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int


# --- Recipes ---------------------------------------------------------------


class RecipeWrite(BaseModel):
    """Create/update payload (moderator only)."""

    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    cuisine: str | None = Field(default=None, max_length=50)
    difficulty: str | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=20000)
    # Structured yield so the site can scale ingredient amounts. Always >= 1; a recipe
    # with no known yield is 1 (the default), not null — see migration 0008.
    servings: int = Field(default=1, ge=1, le=1000)
    ingredients: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    hero_image_url: str | None = Field(default=None, max_length=500)
    video_key: str | None = Field(default=None, max_length=300)
    published: bool = False

    @field_validator("difficulty")
    @classmethod
    def _known_difficulty(cls, v: str | None) -> str | None:
        if v is not None and v not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        return v


class RecipePublic(BaseModel):
    """What readers see."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    category: str | None
    cuisine: str | None
    difficulty: str | None
    summary: str | None
    notes: str | None
    servings: int
    ingredients: list[str]
    steps: list[str]
    hero_image_url: str | None
    video_key: str | None


class RecipeAdmin(RecipePublic):
    """What an author sees — includes draft state and id."""

    id: uuid.UUID
    published: bool
    created_at: datetime
    updated_at: datetime


class RecipeImportRequest(BaseModel):
    """URL to import a recipe from (moderator only)."""

    url: str = Field(min_length=1, max_length=2000)


class UploadPresignRequest(BaseModel):
    """Ask for a presigned S3 PUT to upload recipe media (moderator only)."""

    kind: str = Field(default="image", pattern="^(image|video)$")
    content_type: str = Field(min_length=3, max_length=100)
    # Optional, only to make the object key human-readable (e.g. the recipe slug).
    slug: str | None = Field(default=None, max_length=200)


class UploadPresignResponse(BaseModel):
    """A short-lived presigned PUT plus what to store on the recipe once uploaded:
    public_url (image → hero_image_url) or video_key (video → video_key)."""

    url: str
    key: str
    headers: dict[str, str]
    public_url: str | None = None
    video_key: str | None = None


# --- Classes ---------------------------------------------------------------

# Basic email shape — enough for a signup form without pulling in email-validator.
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ToolItem(BaseModel):
    """One product used in a class — an Amazon affiliate link. The URL is stored
    raw (no `?tag=`); the site injects the Associates tag at render time (md.js)."""

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("url must start with http:// or https://")
        return v


class ClassWrite(BaseModel):
    """Create/update payload for a class (moderator only)."""

    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=20000)
    tools: list[ToolItem] = Field(default_factory=list, max_length=100)
    hero_image_url: str | None = Field(default=None, max_length=500)
    published: bool = False
    sort_order: int = 0


class ClassSessionWrite(BaseModel):
    """Create/update payload for a scheduled session (moderator only)."""

    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    location: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    status: str = Field(default="scheduled", pattern="^(scheduled|cancelled)$")
    price_cents: int | None = Field(default=None, ge=0)  # reserved for future payment
    notes: str | None = Field(default=None, max_length=2000)


class ClassSessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starts_at: datetime
    duration_minutes: int | None
    location: str | None
    capacity: int | None
    status: str
    spots_left: int | None = None  # computed by the router; null = unlimited


class ClassPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    summary: str | None
    description: str | None
    tools: list[ToolItem] = Field(default_factory=list)
    hero_image_url: str | None
    sessions: list[ClassSessionPublic] = Field(default_factory=list)


class ClassAdmin(ClassPublic):
    id: uuid.UUID
    published: bool
    sort_order: int


class ClassSignupWrite(BaseModel):
    """A public signup for a scheduled session (name + email, no login)."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=_EMAIL, max_length=255)
    party_size: int = Field(default=1, ge=1, le=20)
    message: str | None = Field(default=None, max_length=2000)
    hp: str | None = Field(default=None, max_length=200)  # honeypot — bots fill it; router silently drops


class ClassRequestWrite(BaseModel):
    """A public request for a class or a new date (name + email, no login)."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=_EMAIL, max_length=255)
    message: str | None = Field(default=None, max_length=2000)
    preferred_timeframe: str | None = Field(default=None, max_length=200)
    hp: str | None = Field(default=None, max_length=0)  # honeypot


class ClassSignupAdmin(BaseModel):
    """A roster row a moderator sees."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    email: str
    party_size: int
    message: str | None
    status: str
    created_at: datetime


class ClassRequestAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID | None
    name: str
    email: str
    message: str | None
    preferred_timeframe: str | None
    created_at: datetime


# --- User administration ----------------------------------------------------


class UserAdmin(BaseModel):
    """A pool user as the admin page sees them."""

    username: str
    email: str | None
    name: str | None
    status: str | None
    enabled: bool
    groups: list[str]


class AccessRequest(BaseModel):
    """A signed-in user asking to be let into a gated area."""

    group: str = Field(default="family", min_length=1, max_length=64)
