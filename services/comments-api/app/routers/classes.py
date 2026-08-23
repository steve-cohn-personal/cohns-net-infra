"""Cooking-class workshops: public class pages + name/email signup & request (no
login), and moderator CRUD for classes, sessions, and the rosters.

Signups/requests are stored (so Steve has a roster) and emailed via SNS. Capacity is
soft: a full session waitlists rather than rejects. Payment is out of scope this
iteration (session.price_cents is carried but unused)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import aws_admin
from app.auth import require_moderator
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Class, ClassRequest, ClassSession, ClassSignup
from app.ratelimit import limiter
from app.schemas import (
    ClassAdmin,
    ClassPublic,
    ClassRequestAdmin,
    ClassRequestWrite,
    ClassSessionPublic,
    ClassSessionWrite,
    ClassSignupAdmin,
    ClassSignupWrite,
    ClassWrite,
)

router = APIRouter(tags=["classes"])
_settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _class_by_slug(session: AsyncSession, slug: str) -> Class | None:
    return (await session.execute(select(Class).where(Class.slug == slug))).scalar_one_or_none()


async def _registered_count(session: AsyncSession, session_id: uuid.UUID) -> int:
    """Sum of party sizes currently holding a registered spot in a session."""
    total = await session.scalar(
        select(func.coalesce(func.sum(ClassSignup.party_size), 0)).where(
            ClassSignup.session_id == session_id, ClassSignup.status == "registered"
        )
    )
    return int(total or 0)


async def _session_public(session: AsyncSession, s: ClassSession) -> ClassSessionPublic:
    spots = None
    if s.capacity is not None:
        spots = max(0, s.capacity - await _registered_count(session, s.id))
    return ClassSessionPublic(
        id=s.id, starts_at=s.starts_at, duration_minutes=s.duration_minutes,
        location=s.location, capacity=s.capacity, status=s.status, spots_left=spots,
    )


async def _upcoming(session: AsyncSession, class_id: uuid.UUID) -> list[ClassSession]:
    result = await session.execute(
        select(ClassSession)
        .where(ClassSession.class_id == class_id, ClassSession.status == "scheduled",
               ClassSession.starts_at >= _now())
        .order_by(ClassSession.starts_at.asc())
    )
    return list(result.scalars())


# --- Public reads -----------------------------------------------------------


@router.get("/classes", response_model=list[ClassPublic])
async def list_classes(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Class).where(Class.published.is_(True)).order_by(Class.sort_order, Class.title)
    )
    classes = list(result.scalars())
    out = []
    for c in classes:
        sessions = [await _session_public(session, s) for s in await _upcoming(session, c.id)]
        out.append(ClassPublic(slug=c.slug, title=c.title, summary=c.summary,
                               description=c.description, tools=c.tools or [],
                               hero_image_url=c.hero_image_url, sessions=sessions))
    return out


@router.get("/classes/{slug}", response_model=ClassPublic)
async def get_class(slug: str, session: AsyncSession = Depends(get_session)):
    c = await _class_by_slug(session, slug)
    if c is None or not c.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")
    sessions = [await _session_public(session, s) for s in await _upcoming(session, c.id)]
    return ClassPublic(slug=c.slug, title=c.title, summary=c.summary,
                       description=c.description, tools=c.tools or [],
                       hero_image_url=c.hero_image_url, sessions=sessions)


# --- Public signup + request (no login; rate-limited; honeypot) -------------


@router.post("/classes/{slug}/sessions/{session_id}/signup", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(_settings.rate_limit_post)
async def signup(
    request: Request,  # required by slowapi to key the rate limit
    slug: str,
    session_id: uuid.UUID,
    payload: ClassSignupWrite,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if payload.hp:  # bot filled the honeypot — pretend success, do nothing
        return {"status": "registered"}
    c = await _class_by_slug(session, slug)
    if c is None or not c.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")
    s = await session.get(ClassSession, session_id)
    if s is None or s.class_id != c.id or s.status != "scheduled":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    # Soft capacity: a full session waitlists rather than rejecting.
    status_ = "registered"
    if s.capacity is not None and await _registered_count(session, s.id) + payload.party_size > s.capacity:
        status_ = "waitlisted"

    session.add(ClassSignup(session_id=s.id, name=payload.name.strip(), email=payload.email.strip(),
                            party_size=payload.party_size, message=payload.message, status=status_))
    await session.commit()

    when = s.starts_at.strftime("%A %B %-d, %Y at %-I:%M %p") + (f" — {s.location}" if s.location else "")
    await run_in_threadpool(
        aws_admin.notify_class_signup, settings, class_title=c.title, when=when, name=payload.name,
        email=payload.email, party_size=payload.party_size, status=status_, message=payload.message,
    )
    return {"status": status_}


@router.post("/classes/{slug}/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(_settings.rate_limit_post)
async def request_class(
    request: Request,
    slug: str,
    payload: ClassRequestWrite,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if payload.hp:
        return {"status": "received"}
    c = await _class_by_slug(session, slug)  # slug may be a real class or a general request
    class_id = c.id if c else None
    session.add(ClassRequest(class_id=class_id, name=payload.name.strip(), email=payload.email.strip(),
                             message=payload.message, preferred_timeframe=payload.preferred_timeframe))
    await session.commit()
    await run_in_threadpool(
        aws_admin.notify_class_request, settings, class_title=(c.title if c else None), name=payload.name,
        email=payload.email, message=payload.message, preferred_timeframe=payload.preferred_timeframe,
    )
    return {"status": "received"}


# --- Class management (moderator only) --------------------------------------


async def _class_admin(session: AsyncSession, c: Class) -> ClassAdmin:
    result = await session.execute(
        select(ClassSession).where(ClassSession.class_id == c.id).order_by(ClassSession.starts_at.asc())
    )
    sessions = [await _session_public(session, s) for s in result.scalars()]
    return ClassAdmin(slug=c.slug, title=c.title, summary=c.summary, description=c.description,
                      tools=c.tools or [], hero_image_url=c.hero_image_url, sessions=sessions, id=c.id,
                      published=c.published, sort_order=c.sort_order)


@router.get("/admin/classes", response_model=list[ClassAdmin], dependencies=[Depends(require_moderator)])
async def list_classes_admin(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Class).order_by(Class.sort_order, Class.title))
    return [await _class_admin(session, c) for c in result.scalars()]


@router.post("/admin/classes", response_model=ClassAdmin, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_moderator)])
async def create_class(payload: ClassWrite, session: AsyncSession = Depends(get_session)):
    c = Class(**payload.model_dump())
    session.add(c)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"slug '{payload.slug}' already exists") from None
    await session.refresh(c)
    return await _class_admin(session, c)


@router.put("/admin/classes/{class_id}", response_model=ClassAdmin, dependencies=[Depends(require_moderator)])
async def update_class(class_id: uuid.UUID, payload: ClassWrite, session: AsyncSession = Depends(get_session)):
    c = await session.get(Class, class_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")
    for field, value in payload.model_dump().items():
        setattr(c, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"slug '{payload.slug}' already exists") from None
    await session.refresh(c)
    return await _class_admin(session, c)


@router.delete("/admin/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_moderator)])
async def delete_class(class_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    c = await session.get(Class, class_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")
    await session.delete(c)  # sessions + signups cascade
    await session.commit()


# --- Session management (moderator only) ------------------------------------


@router.post("/admin/classes/{class_id}/sessions", response_model=ClassSessionPublic,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_moderator)])
async def create_session(class_id: uuid.UUID, payload: ClassSessionWrite, session: AsyncSession = Depends(get_session)):
    if await session.get(Class, class_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "class not found")
    s = ClassSession(class_id=class_id, **payload.model_dump())
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return await _session_public(session, s)


@router.put("/admin/classes/sessions/{session_id}", response_model=ClassSessionPublic,
            dependencies=[Depends(require_moderator)])
async def update_session(session_id: uuid.UUID, payload: ClassSessionWrite, session: AsyncSession = Depends(get_session)):
    s = await session.get(ClassSession, session_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    for field, value in payload.model_dump().items():
        setattr(s, field, value)
    await session.commit()
    await session.refresh(s)
    return await _session_public(session, s)


@router.delete("/admin/classes/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_moderator)])
async def delete_session(session_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    s = await session.get(ClassSession, session_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    await session.delete(s)
    await session.commit()


# --- Rosters (moderator only) -----------------------------------------------


@router.get("/admin/classes/{class_id}/signups", response_model=list[ClassSignupAdmin],
            dependencies=[Depends(require_moderator)])
async def class_signups(class_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ClassSignup)
        .join(ClassSession, ClassSignup.session_id == ClassSession.id)
        .where(ClassSession.class_id == class_id)
        .order_by(ClassSignup.created_at.desc())
    )
    return list(result.scalars())


@router.get("/admin/class-requests", response_model=list[ClassRequestAdmin],
            dependencies=[Depends(require_moderator)])
async def class_requests(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ClassRequest).order_by(ClassRequest.created_at.desc()))
    return list(result.scalars())
