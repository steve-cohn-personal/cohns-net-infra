from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_user
from app.config import get_settings
from app.db import get_session
from app.models import Comment, CommentStatus
from app.ratelimit import limiter
from app.schemas import CommentAdmin, CommentCreate, CommentPublic

router = APIRouter(tags=["comments"])
_settings = get_settings()


@router.get("/comments", response_model=list[CommentPublic])
async def list_comments(page_slug: str, session: AsyncSession = Depends(get_session)):
    """Public read path — only ever returns approved comments."""
    result = await session.execute(
        select(Comment)
        .where(Comment.page_slug == page_slug, Comment.status == CommentStatus.approved)
        .order_by(Comment.created_at.asc())
    )
    return list(result.scalars())


@router.post("/comments", response_model=CommentAdmin, status_code=status.HTTP_201_CREATED)
@limiter.limit(_settings.rate_limit_post)
async def create_comment(
    request: Request,  # required by slowapi to key the rate limit
    payload: CommentCreate,
    user: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Authenticated post. Lands as `pending` — invisible until moderated."""
    comment = Comment(
        page_slug=payload.page_slug,
        author_sub=user.sub,
        author_name=user.name,
        body=payload.body,
        status=CommentStatus.pending,
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment
