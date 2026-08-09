import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import CommentStatus


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


# --- Recipes ---------------------------------------------------------------


class RecipeWrite(BaseModel):
    """Create/update payload (moderator only)."""

    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    summary: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=20000)
    ingredients: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    hero_image_url: str | None = Field(default=None, max_length=500)
    video_key: str | None = Field(default=None, max_length=300)
    published: bool = False


class RecipePublic(BaseModel):
    """What readers see."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    category: str | None
    summary: str | None
    notes: str | None
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
    """A short-lived presigned PUT plus the public URL the object will have."""

    url: str
    key: str
    headers: dict[str, str]
    public_url: str


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
