"""recipe category

Adds a nullable, indexed `category` column to recipes and backfills existing rows
to 'Main Courses' (the 7 seeded recipes are paellas + broths). Non-destructive and
reversible.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("category", sa.String(length=50), nullable=True))
    op.create_index("ix_recipes_category", "recipes", ["category"])
    # Backfill: everything that predates categories becomes a Main Course.
    op.execute(sa.text("UPDATE recipes SET category = 'Main Courses' WHERE category IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_recipes_category", table_name="recipes")
    op.drop_column("recipes", "category")
