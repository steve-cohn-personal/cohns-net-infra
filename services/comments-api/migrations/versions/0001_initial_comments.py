"""initial comments table

Revision ID: 0001
Revises:
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("page_slug", sa.String(length=200), nullable=False),
        sa.Column("author_sub", sa.String(length=255), nullable=False),
        sa.Column("author_name", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="comment_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderated_by", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_comments_page_slug", "comments", ["page_slug"])
    op.create_index("ix_comments_author_sub", "comments", ["author_sub"])
    op.create_index("ix_comments_status", "comments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_comments_status", table_name="comments")
    op.drop_index("ix_comments_author_sub", table_name="comments")
    op.drop_index("ix_comments_page_slug", table_name="comments")
    op.drop_table("comments")
    sa.Enum(name="comment_status").drop(op.get_bind(), checkfirst=True)
