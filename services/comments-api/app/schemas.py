import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

# The fixed set of recipe categories, in display order. A recipe's category is
# optional (null = uncategorized); anything else must be one of these. Kept here so
# the schema, the /recipes/categories endpoint, and the front-end share one source.
CATEGORIES: tuple[str, ...] = (
    "Breads",
    "Candy",
    "Quick Meals",
    "Appetizers",
    "Main Courses",
    "Desserts",
)


class RecipeWrite(BaseModel):
    """Create/update payload (moderator only)."""

    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    summary: str | None = Field(default=None, max_length=2000)
    ingredients: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    hero_image_url: str | None = Field(default=None, max_length=500)
    video_key: str | None = Field(default=None, max_length=300)
    published: bool = False

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str | None) -> str | None:
        if v is not None and v not in CATEGORIES:
            raise ValueError(f"category must be null or one of: {', '.join(CATEGORIES)}")
        return v


class RecipePublic(BaseModel):
    """What readers see."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    category: str | None
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
