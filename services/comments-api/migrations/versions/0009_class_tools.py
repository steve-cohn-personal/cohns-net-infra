"""class tools column

Adds a structured `tools` list to classes: the products used in a class, each an
Amazon affiliate link, stored as JSON [{name, url, note}]. Nullable — existing
classes come back as an empty list (the router coerces NULL -> []), and any edit
backfills the column. URLs are stored raw; the site injects the Associates tag at
render time (site/js/md.js).

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("classes", sa.Column("tools", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("classes", "tools")
