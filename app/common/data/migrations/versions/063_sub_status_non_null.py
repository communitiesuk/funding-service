"""make submission status non-nullable

Revision ID: 063_sub_status_non_null
Revises: 062_add_submission_status
Create Date: 2026-06-01 22:04:18.753335

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "063_sub_status_non_null"
down_revision = "062_add_submission_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=postgresql.ENUM(
                "NOT_STARTED",
                "IN_PROGRESS",
                "READY_TO_SUBMIT",
                "AWAITING_SIGN_OFF",
                "SUBMITTED",
                "NOT_SUBMITTED",
                "PARTIALLY_SUBMITTED",
                name="submission_status_enum",
            ),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=postgresql.ENUM(
                "NOT_STARTED",
                "IN_PROGRESS",
                "READY_TO_SUBMIT",
                "AWAITING_SIGN_OFF",
                "SUBMITTED",
                "NOT_SUBMITTED",
                "PARTIALLY_SUBMITTED",
                name="submission_status_enum",
            ),
            nullable=True,
        )
