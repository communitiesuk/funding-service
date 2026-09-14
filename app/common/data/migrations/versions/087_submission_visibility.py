"""Add collection submission visibility

Revision ID: 087_submission_visibility
Revises: 086_allow_edits_after_deadline
Create Date: 2026-09-14 23:36:22.453694

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "087_submission_visibility"
down_revision = "086_allow_edits_after_deadline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum(
        "ALWAYS_VISIBLE", "REQUIRES_SUBMITTED_STATUS", "REQUIRES_CLOSED_COLLECTION", name="submission_visibility"
    ).create(op.get_bind())
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "submission_visibility",
                postgresql.ENUM(
                    "ALWAYS_VISIBLE",
                    "REQUIRES_SUBMITTED_STATUS",
                    "REQUIRES_CLOSED_COLLECTION",
                    name="submission_visibility",
                    create_type=False,
                ),
                nullable=True,
            )
        )

    op.execute(
        """
        UPDATE collection SET submission_visibility = CASE
            WHEN allow_public_sign_up THEN 'REQUIRES_CLOSED_COLLECTION'::submission_visibility
            ELSE 'ALWAYS_VISIBLE'::submission_visibility
        END
        """
    )

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.alter_column("submission_visibility", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("submission_visibility")

    sa.Enum(
        "ALWAYS_VISIBLE", "REQUIRES_SUBMITTED_STATUS", "REQUIRES_CLOSED_COLLECTION", name="submission_visibility"
    ).drop(op.get_bind())
