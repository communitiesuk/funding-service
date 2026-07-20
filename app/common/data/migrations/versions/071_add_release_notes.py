"""add the release note model

Revision ID: 071_add_release_notes
Revises: 070_add_assessment_status_col
Create Date: 2026-07-20 14:43:50.519137

"""

import sqlalchemy as sa
from alembic import op

revision = "071_add_release_notes"
down_revision = "070_add_assessment_status_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_note",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_note")),
    )


def downgrade() -> None:
    op.drop_table("release_note")
