"""Strip the legacy question_id key from every Expression.context JSONB blob.

Revision ID: 058_drop_legacy_question_id
Revises: 057_swap_depends_on_ref_idx
Create Date: 2026-04-16 16:13:00.494020
"""

from alembic import op

revision = "058_drop_legacy_question_id"
down_revision = "057_swap_depends_on_ref_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE expression SET context = context - 'question_id' WHERE context ? 'question_id'")


def downgrade() -> None:
    # No going back!
    pass
