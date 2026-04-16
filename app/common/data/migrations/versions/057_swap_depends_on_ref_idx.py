"""Swap the managed-condition uniqueness index to subject_reference.

Revision ID: 057_swap_depends_on_ref_idx
Revises: 056_component_ref_column_deps
Create Date: 2026-04-16 11:30:03.139641
"""

import sqlalchemy as sa
from alembic import op

revision = "057_swap_depends_on_ref_idx"
down_revision = "056_component_ref_column_deps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill subject_reference on any managed-expression row that's still missing it.
    # Dual-write from deploy 1 should mean this is a no-op for almost all rows, but cover
    # anything written before deploy 1 rolled.
    op.execute(
        """
        UPDATE expression
        SET context = jsonb_set(
            context,
            '{subject_reference}',
            to_jsonb('q_' || replace(context ->> 'question_id', '-', ''))
        )
        WHERE managed_name IS NOT NULL
          AND context ->> 'question_id' IS NOT NULL
          AND NOT (context ? 'subject_reference')
        """
    )

    # Swap the uniqueness index to key on subject_reference.
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("uq_type_condition_unique_question"),
            postgresql_where="((type = 'CONDITION'::expression_type_enum) AND (managed_name IS NOT NULL))",
        )
        batch_op.create_index(
            "uq_type_condition_unique_question",
            ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'subject_reference')")],  # ty: ignore[invalid-argument-type]
            unique=True,
            postgresql_where="type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_type_condition_unique_question",
            postgresql_where="type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL",
        )
        batch_op.create_index(
            batch_op.f("uq_type_condition_unique_question"),
            ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'question_id'::text)")],  # ty: ignore[invalid-argument-type]
            unique=True,
            postgresql_where="((type = 'CONDITION'::expression_type_enum) AND (managed_name IS NOT NULL))",
        )
