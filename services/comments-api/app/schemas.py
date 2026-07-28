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
