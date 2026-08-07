"""categories table

Turns the recipe categories from a hardcoded constant into data. Creates the
`categories` table and seeds the six original names in their display order.
`recipes.category` (the denormalized name) is unchanged.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SEED = ["Breads", "Candy", "Quick Meals", "Appetizers", "Main Courses", "Desserts"]


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_categories_name", "categories", ["name"], unique=True)
    op.create_index("ix_categories_sort_order", "categories", ["sort_order"])

    op.bulk_insert(
        categories,
        [{"id": uuid.uuid4(), "name": name, "sort_order": i} for i, name in enumerate(SEED)],
    )


def downgrade() -> None:
    op.drop_index("ix_categories_sort_order", table_name="categories")
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_table("categories")
