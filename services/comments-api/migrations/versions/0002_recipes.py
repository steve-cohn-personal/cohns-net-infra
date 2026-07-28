"""recipes table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("hero_image_url", sa.String(length=500), nullable=True),
        sa.Column("video_key", sa.String(length=300), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recipes_slug", "recipes", ["slug"], unique=True)
    op.create_index("ix_recipes_published", "recipes", ["published"])


def downgrade() -> None:
    op.drop_index("ix_recipes_published", table_name="recipes")
    op.drop_index("ix_recipes_slug", table_name="recipes")
    op.drop_table("recipes")
