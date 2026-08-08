"""recipe notes

Adds a nullable `notes` column to recipes — a longer Markdown "story" (headnote,
background, tips), rendered to sanitized HTML on the site. Non-destructive.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "notes")
