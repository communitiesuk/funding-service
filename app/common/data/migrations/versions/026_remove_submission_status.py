"""empty message

Revision ID: 026_remove_submission_status
Revises: 025_ds_item_key_case_insensitive
Create Date: 2025-08-08 10:41:55.178484

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "026_remove_submission_status"
down_revision = "025_ds_item_key_case_insensitive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_column("status")

    sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="submission_status_enum").drop(op.get_bind())


def downgrade() -> None:
    sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="submission_status_enum").create(op.get_bind())
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                postgresql.ENUM(
                    "NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="submission_status_enum", create_type=False
                ),
                autoincrement=False,
                nullable=False,
            )
        )
