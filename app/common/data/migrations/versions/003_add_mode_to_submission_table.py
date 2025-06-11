"""add mode column to submission table

Revision ID: 003_add_mode_to_submission_table
Revises: 002_adding_name_column
Create Date: 2025-06-11 08:53:52.299045

"""

import sqlalchemy as sa
from alembic import op

revision = "003_add_mode_to_submission_table"
down_revision = "002_adding_name_column"
branch_labels = None
depends_on = None

submission_mode_enum = sa.Enum("TEST", "LIVE", name="submission_mode_enum")


def upgrade() -> None:
    submission_mode_enum.create(op.get_bind())

    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mode", submission_mode_enum, nullable=True))

    op.execute("UPDATE submission SET mode = 'TEST' WHERE mode IS NULL;")

    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.alter_column("mode", nullable=False, existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_column("mode")

    submission_mode_enum.drop(op.get_bind())
