from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_moderator
from app.db import get_session
from app.models import Recipe
from app.schemas import CATEGORIES, RecipeAdmin, RecipePublic, RecipeWrite

router = APIRouter(tags=["recipes"])


# --- Public reads -----------------------------------------------------------


@router.get("/recipes/categories", response_model=list[str])
async def list_categories():
    """The fixed category vocabulary, in display order — one source for the front-end."""
    return list(CATEGORIES)


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


@router.post(
    "/recipes",
    response_model=RecipeAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_moderator)],
)
async def create_recipe(payload: RecipeWrite, session: AsyncSession = Depends(get_session)):
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

    for field, value in payload.model_dump().items():
        setattr(recipe, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"slug '{payload.slug}' already exists") from None
    await session.refresh(recipe)
    return recipe


async def _by_slug(session: AsyncSession, slug: str) -> Recipe | None:
    result = await session.execute(select(Recipe).where(Recipe.slug == slug))
    return result.scalar_one_or_none()
