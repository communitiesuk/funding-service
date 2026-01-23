"""Backfill Expression context with collection_id

Revision ID: 036_backfill_expression_context
Revises: 035_remove_static_event_data
Create Date: 2026-01-23

"""

from alembic import op

revision = "036_backfill_expression_context"
down_revision = "035_remove_static_event_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE expression e
        SET context = e.context || jsonb_build_object('collection_id', f.collection_id::text)
        FROM component c
        JOIN form f ON c.form_id = f.id
        WHERE e.question_id = c.id
          AND e.context->>'collection_id' IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE expression
        SET context = context - 'collection_id'
        """
    )
