"""classes, class_sessions, class_signups, class_requests

The cooking-class area: authored classes (like recipes), scheduled sessions people
sign up for, plus stored signups and class requests. Seeds three placeholder classes
(published, no sessions yet → request-only until scheduled). Payment fields
(session.price_cents, signup.status) are present but unused this iteration.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-11
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SEED_CLASSES = [
    ("paella", "Paella", "A hands-on Spanish paella workshop — build a proper socarrat from scratch."),
    ("knife-skills", "Knife Skills", "Grip, stance, and the core cuts. Leave dicing an onion in seconds."),
    ("christmas-candy-workshop", "Christmas Candy Workshop", "Brittles, fudge, and toffee — a festive candy-making session."),
]


def upgrade() -> None:
    classes = op.create_table(
        "classes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hero_image_url", sa.String(length=500), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_classes_slug", "classes", ["slug"], unique=True)
    op.create_index("ix_classes_published", "classes", ["published"])
    op.create_index("ix_classes_sort_order", "classes", ["sort_order"])

    op.create_table(
        "class_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("class_id", sa.Uuid(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="scheduled"),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_class_sessions_class_id", "class_sessions", ["class_id"])
    op.create_index("ix_class_sessions_starts_at", "class_sessions", ["starts_at"])

    op.create_table(
        "class_signups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="registered"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_class_signups_session_id", "class_signups", ["session_id"])

    op.create_table(
        "class_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("class_id", sa.Uuid(), sa.ForeignKey("classes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("preferred_timeframe", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_class_requests_class_id", "class_requests", ["class_id"])

    op.bulk_insert(
        classes,
        [
            {"id": uuid.uuid4(), "slug": slug, "title": title, "summary": summary,
             "description": None, "hero_image_url": None, "published": True, "sort_order": i}
            for i, (slug, title, summary) in enumerate(SEED_CLASSES)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_class_requests_class_id", table_name="class_requests")
    op.drop_table("class_requests")
    op.drop_index("ix_class_signups_session_id", table_name="class_signups")
    op.drop_table("class_signups")
    op.drop_index("ix_class_sessions_starts_at", table_name="class_sessions")
    op.drop_index("ix_class_sessions_class_id", table_name="class_sessions")
    op.drop_table("class_sessions")
    op.drop_index("ix_classes_sort_order", table_name="classes")
    op.drop_index("ix_classes_published", table_name="classes")
    op.drop_index("ix_classes_slug", table_name="classes")
    op.drop_table("classes")
