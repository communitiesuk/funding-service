"""user email check constraint

Revision ID: 043_user_email_check
Revises: 042_remove_allow_decimals
Create Date: 2026-02-13 16:51:40.837604

"""

from alembic import op

revision = "043_user_email_check"
down_revision = "042_remove_allow_decimals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_email_no_smart_quotes"),
            "email NOT LIKE '%’%'",
        )


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_email_no_smart_quotes"), type_="check")
