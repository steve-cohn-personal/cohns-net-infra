import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import media_uploads, recipe_import
from app.auth import require_moderator
from app.config import Settings, get_settings
from app.db import get_session
from app.media_uploads import UploadError
from app.models import Category, Cuisine, Recipe
from app.recipe_import import RecipeImportError
from app.schemas import (
    CategoryPublic,
    CategoryWrite,
    CuisinePublic,
    CuisineWrite,
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


@router.get("/recipes/cuisines", response_model=list[str])
async def list_cuisine_names(session: AsyncSession = Depends(get_session)):
    """The cuisine vocabulary, in display order (moderator-maintained, like categories)."""
    result = await session.execute(select(Cuisine.name).order_by(Cuisine.sort_order, Cuisine.name))
    return list(result.scalars())


@router.get("/recipes", response_model=list[RecipePublic])
async def list_recipes(
    q: str | None = None,
    category: str | None = None,
    cuisine: str | None = None,
    difficulty: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Published recipes, optionally filtered by a free-text query and/or facets.
    `q` matches (case-insensitively) across title, summary, notes, and the ingredient
    and step text. `contains`/`func.lower` keep it portable across Postgres and the
    SQLite test DB (no ILIKE)."""
    stmt = select(Recipe).where(Recipe.published.is_(True))
    if category is not None:
        stmt = stmt.where(Recipe.category == category)
    if cuisine is not None:
        stmt = stmt.where(Recipe.cuisine == cuisine)
    if difficulty is not None:
        stmt = stmt.where(Recipe.difficulty == difficulty)
    if q and q.strip():
        needle = q.strip().lower()
        stmt = stmt.where(
            or_(
                func.lower(Recipe.title).contains(needle),
                func.lower(func.coalesce(Recipe.summary, "")).contains(needle),
                func.lower(func.coalesce(Recipe.notes, "")).contains(needle),
                func.lower(cast(Recipe.ingredients, String)).contains(needle),
                func.lower(cast(Recipe.steps, String)).contains(needle),
            )
        )
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
    await _ensure_valid_cuisine(session, payload.cuisine)
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
    await _ensure_valid_cuisine(session, payload.cuisine)

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


# --- Cuisine management (moderator only) ------------------------------------


@router.get("/admin/cuisines", response_model=list[CuisinePublic], dependencies=[Depends(require_moderator)])
async def list_cuisines_admin(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Cuisine).order_by(Cuisine.sort_order, Cuisine.name))
    return list(result.scalars())


@router.post(
    "/admin/cuisines",
    response_model=CuisinePublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_moderator)],
)
async def create_cuisine(payload: CuisineWrite, session: AsyncSession = Depends(get_session)):
    cuisine = Cuisine(name=payload.name.strip(), sort_order=payload.sort_order)
    session.add(cuisine)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"cuisine '{payload.name}' already exists") from None
    await session.refresh(cuisine)
    return cuisine


@router.put(
    "/admin/cuisines/{cuisine_id}",
    response_model=CuisinePublic,
    dependencies=[Depends(require_moderator)],
)
async def update_cuisine(
    cuisine_id: uuid.UUID, payload: CuisineWrite, session: AsyncSession = Depends(get_session)
):
    cuisine = await session.get(Cuisine, cuisine_id)
    if cuisine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cuisine not found")

    old_name, new_name = cuisine.name, payload.name.strip()
    cuisine.name = new_name
    cuisine.sort_order = payload.sort_order
    # A rename cascades to every recipe carrying the old (denormalized) name.
    if new_name != old_name:
        await session.execute(update(Recipe).where(Recipe.cuisine == old_name).values(cuisine=new_name))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"cuisine '{new_name}' already exists") from None
    await session.refresh(cuisine)
    return cuisine


@router.delete(
    "/admin/cuisines/{cuisine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_moderator)],
)
async def delete_cuisine(cuisine_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    cuisine = await session.get(Cuisine, cuisine_id)
    if cuisine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cuisine not found")
    in_use = await session.scalar(
        select(func.count()).select_from(Recipe).where(Recipe.cuisine == cuisine.name)
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cuisine '{cuisine.name}' is used by {in_use} recipe(s); reassign them first",
        )
    await session.delete(cuisine)
    await session.commit()


async def _ensure_valid_category(session: AsyncSession, name: str | None) -> None:
    """A recipe's category must be null or the name of an existing category."""
    if name is None:
        return
    exists = await session.scalar(select(Category.id).where(Category.name == name))
    if exists is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"category '{name}' does not exist")


async def _ensure_valid_cuisine(session: AsyncSession, name: str | None) -> None:
    """A recipe's cuisine must be null or the name of an existing cuisine."""
    if name is None:
        return
    exists = await session.scalar(select(Cuisine.id).where(Cuisine.name == name))
    if exists is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"cuisine '{name}' does not exist")


async def _by_slug(session: AsyncSession, slug: str) -> Recipe | None:
    result = await session.execute(select(Recipe).where(Recipe.slug == slug))
    return result.scalar_one_or_none()
