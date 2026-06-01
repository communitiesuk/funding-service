"""add a submission status column

Revision ID: 062_add_submission_status
Revises: 061_pre_award_collections
Create Date: 2026-06-01 11:36:07.895477

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "062_add_submission_status"
down_revision = "061_pre_award_collections"
branch_labels = None
depends_on = None

submission_status_enum = sa.Enum(
    "NOT_STARTED",
    "IN_PROGRESS",
    "READY_TO_SUBMIT",
    "AWAITING_SIGN_OFF",
    "SUBMITTED",
    "NOT_SUBMITTED",
    "PARTIALLY_SUBMITTED",
    name="submission_status_enum",
)


def upgrade() -> None:
    submission_status_enum.create(op.get_bind())
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                submission_status_enum,
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_column("status")

    submission_status_enum.drop(op.get_bind())
