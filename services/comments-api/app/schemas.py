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


# --- Recipes ---------------------------------------------------------------


class RecipeWrite(BaseModel):
    """Create/update payload (moderator only)."""

    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
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
    summary: str | None
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
