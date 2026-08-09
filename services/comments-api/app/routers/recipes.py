import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import media_uploads, recipe_import
from app.auth import require_moderator
from app.config import Settings, get_settings
from app.db import get_session
from app.media_uploads import UploadError
from app.models import Category, Recipe
from app.recipe_import import RecipeImportError
from app.schemas import (
    CategoryPublic,
    CategoryWrite,
    RecipeAdmin,
    RecipeImportRequest,
    RecipePublic,
    RecipeWrite,
    UploadPresignRequest,
    UploadPresignResponse,
)

router = APIRouter(tags=["recipes"])


# --- Public reads -----------------------------------------------------------


@router.get("/recipes/categories", response_model=list[str])
async def list_category_names(session: AsyncSession = Depends(get_session)):
    """The category vocabulary, in display order — one source for the front-end.
    Reads the categories table, so moderator edits show up everywhere."""
    result = await session.execute(select(Category.name).order_by(Category.sort_order, Category.name))
    return list(result.scalars())


@router.get("/recipes", response_model=list[RecipePublic])
async def list_recipes(category: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Recipe).where(Recipe.published.is_(True))
    if category is not None:
        stmt = stmt.where(Recipe.category == category)
    result = await session.execute(stmt.order_by(Recipe.title.asc()))
    return list(result.scalars())


@router.get("/recipes/{slug}", response_model=RecipePublic)
async def get_recipe(slug: str, session: AsyncSession = Depends(get_session)):
    recipe = await _by_slug(session, slug)
    if recipe is None or not recipe.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")
    return recipe


# --- Authoring (moderator only) --------------------------------------------


@router.get("/admin/recipes", response_model=list[RecipeAdmin], dependencies=[Depends(require_moderator)])
async def list_all_recipes(session: AsyncSession = Depends(get_session)):
    """Every recipe, including drafts."""
    result = await session.execute(select(Recipe).order_by(Recipe.updated_at.desc()))
    return list(result.scalars())


@router.post("/admin/recipes/import", response_model=RecipeWrite, dependencies=[Depends(require_moderator)])
async def import_recipe(payload: RecipeImportRequest):
    """Fetch a URL's schema.org/Recipe JSON-LD and return an unsaved draft for the
    admin to review, categorize, and save. Fetch runs in a threadpool so the blocking
    HTTP call doesn't stall the event loop."""
    try:
        return await run_in_threadpool(recipe_import.import_from_url, payload.url)
    except RecipeImportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None


@router.post(
    "/admin/uploads/presign",
    response_model=UploadPresignResponse,
    dependencies=[Depends(require_moderator)],
)
async def presign_upload(payload: UploadPresignRequest, settings: Settings = Depends(get_settings)):
    """Mint a short-lived presigned S3 PUT so a moderator can upload recipe media
    straight from the browser. 400 on a bad kind/content-type; 503 where uploads
    aren't configured (local, tests, dev — there is no dev media stack). Blocking
    boto3 call runs in a threadpool."""
    try:
        result = await run_in_threadpool(
            media_uploads.presign_put, payload.kind, payload.content_type, payload.slug, settings
        )
    except UploadError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    if result is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "media uploads are not configured")
    return result


@router.post(
    "/recipes",
    response_model=RecipeAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_moderator)],
)
async def create_recipe(payload: RecipeWrite, session: AsyncSession = Depends(get_session)):
    await _ensure_valid_category(session, payload.category)
    recipe = Recipe(**payload.model_dump())
    session.add(recipe)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"slug '{payload.slug}' already exists") from None
    await session.refresh(recipe)
    return recipe


@router.put("/recipes/{slug}", response_model=RecipeAdmin, dependencies=[Depends(require_moderator)])
async def update_recipe(slug: str, payload: RecipeWrite, session: AsyncSession = Depends(get_session)):
    recipe = await _by_slug(session, slug)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")
    await _ensure_valid_category(session, payload.category)

    for field, value in payload.model_dump().items():
        setattr(recipe, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"slug '{payload.slug}' already exists") from None
    await session.refresh(recipe)
    return recipe


@router.delete(
    "/recipes/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_moderator)],
)
async def delete_recipe(slug: str, session: AsyncSession = Depends(get_session)):
    recipe = await _by_slug(session, slug)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")
    await session.delete(recipe)
    await session.commit()


# --- Category management (moderator only) -----------------------------------


@router.get("/admin/categories", response_model=list[CategoryPublic], dependencies=[Depends(require_moderator)])
async def list_categories_admin(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Category).order_by(Category.sort_order, Category.name))
    return list(result.scalars())


@router.post(
    "/admin/categories",
    response_model=CategoryPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_moderator)],
)
async def create_category(payload: CategoryWrite, session: AsyncSession = Depends(get_session)):
    category = Category(name=payload.name.strip(), sort_order=payload.sort_order)
    session.add(category)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"category '{payload.name}' already exists") from None
    await session.refresh(category)
    return category


@router.put(
    "/admin/categories/{category_id}",
    response_model=CategoryPublic,
    dependencies=[Depends(require_moderator)],
)
async def update_category(
    category_id: uuid.UUID, payload: CategoryWrite, session: AsyncSession = Depends(get_session)
):
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")

    old_name, new_name = category.name, payload.name.strip()
    category.name = new_name
    category.sort_order = payload.sort_order
    # A rename cascades to every recipe carrying the old (denormalized) name.
    if new_name != old_name:
        await session.execute(update(Recipe).where(Recipe.category == old_name).values(category=new_name))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"category '{new_name}' already exists") from None
    await session.refresh(category)
    return category


@router.delete(
    "/admin/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_moderator)],
)
async def delete_category(category_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    in_use = await session.scalar(
        select(func.count()).select_from(Recipe).where(Recipe.category == category.name)
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"category '{category.name}' is used by {in_use} recipe(s); reassign them first",
        )
    await session.delete(category)
    await session.commit()


async def _ensure_valid_category(session: AsyncSession, name: str | None) -> None:
    """A recipe's category must be null or the name of an existing category."""
    if name is None:
        return
    exists = await session.scalar(select(Category.id).where(Category.name == name))
    if exists is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"category '{name}' does not exist")


async def _by_slug(session: AsyncSession, slug: str) -> Recipe | None:
    result = await session.execute(select(Recipe).where(Recipe.slug == slug))
    return result.scalar_one_or_none()
