"""recipe servings column

Adds a structured `servings` count to recipes so the site can scale ingredient
amounts up/down, instead of the yield being buried in prose in the summary. The
column is NOT NULL with a server default of 1, so every existing recipe is forced
to 1 on upgrade. Where a serving count can be recovered from the summary text (e.g.
"Serves 2"), scripts/backfill_servings.py sets it afterward and lists the ones that
stayed at 1 for review.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column("servings", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("recipes", "servings")
