"""set up grant recipient to submissions relationship

Revision ID: 012_grant_recipient_relationship
Revises: 011_set_up_grant_recipients
Create Date: 2025-10-29 08:57:24.396260

"""

import sqlalchemy as sa
from alembic import op

revision = "012_grant_recipient_relationship"
down_revision = "011_set_up_grant_recipients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.add_column(sa.Column("grant_recipient_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_submission_grant_recipient_id_grant_recipient"),
            "grant_recipient",
            ["grant_recipient_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_grant_recipient_if_live",
            "mode = 'TEST' OR grant_recipient_id IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_constraint("ck_grant_recipient_if_live", type_="check")
        batch_op.drop_constraint(batch_op.f("fk_submission_grant_recipient_id_grant_recipient"), type_="foreignkey")
        batch_op.drop_column("grant_recipient_id")
