"""Change submission status to not allow nulls

Revision ID: 063_submission_status_not_null
Revises: 062_add_submission_status
Create Date: 2026-06-03 15:17:30.589089

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "063_submission_status_not_null"
down_revision = "062_add_submission_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=postgresql.ENUM(name="submission_status_enum", create_type=False),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=postgresql.ENUM(name="submission_status_enum", create_type=False),
            nullable=True,
        )
