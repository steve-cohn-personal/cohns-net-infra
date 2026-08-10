"""cuisines table + recipe cuisine/difficulty columns

Adds a moderator-maintained `cuisines` vocabulary (mirrors `categories`) seeded with
a starter set, plus two nullable recipe columns: `cuisine` (validated against the
table) and `difficulty` (a hard-coded Easy/Medium/Hard, validated in the schema).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-10
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SEED = ["American", "Italian", "Spanish", "Mexican", "French", "Mediterranean", "Asian"]


def upgrade() -> None:
    cuisines = op.create_table(
        "cuisines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cuisines_name", "cuisines", ["name"], unique=True)
    op.create_index("ix_cuisines_sort_order", "cuisines", ["sort_order"])
    op.bulk_insert(
        cuisines,
        [{"id": uuid.uuid4(), "name": name, "sort_order": i} for i, name in enumerate(SEED)],
    )

    op.add_column("recipes", sa.Column("cuisine", sa.String(length=50), nullable=True))
    op.add_column("recipes", sa.Column("difficulty", sa.String(length=20), nullable=True))
    op.create_index("ix_recipes_cuisine", "recipes", ["cuisine"])
    op.create_index("ix_recipes_difficulty", "recipes", ["difficulty"])


def downgrade() -> None:
    op.drop_index("ix_recipes_difficulty", table_name="recipes")
    op.drop_index("ix_recipes_cuisine", table_name="recipes")
    op.drop_column("recipes", "difficulty")
    op.drop_column("recipes", "cuisine")
    op.drop_index("ix_cuisines_sort_order", table_name="cuisines")
    op.drop_index("ix_cuisines_name", table_name="cuisines")
    op.drop_table("cuisines")
