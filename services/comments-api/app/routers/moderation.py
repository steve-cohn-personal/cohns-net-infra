import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require_moderator
from app.db import get_session
from app.models import Comment, CommentStatus
from app.schemas import CommentAdmin, ModerationAction

router = APIRouter(prefix="/admin", tags=["moderation"], dependencies=[Depends(require_moderator)])


@router.get("/comments", response_model=list[CommentAdmin])
async def list_for_moderation(
    status_filter: CommentStatus = CommentStatus.pending,
    session: AsyncSession = Depends(get_session),
):
    """The moderation queue. Defaults to everything still pending."""
    result = await session.execute(
        select(Comment).where(Comment.status == status_filter).order_by(Comment.created_at.asc())
    )
    return list(result.scalars())


@router.post("/comments/{comment_id}/moderate", response_model=CommentAdmin)
async def moderate(
    comment_id: uuid.UUID,
    action: ModerationAction,
    moderator: Principal = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
):
    if action.decision not in (CommentStatus.approved, CommentStatus.rejected):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "decision must be approved or rejected")

    comment = await session.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comment not found")

    comment.status = action.decision
    comment.moderated_at = datetime.now(timezone.utc)
    comment.moderated_by = moderator.sub
    await session.commit()
    await session.refresh(comment)
    return comment
