"""stop grant recipients from manually creating new submissions for managed multi-submission collections

Revision ID: 048_multi_submissions_managed
Revises: 047_non_null_external_id
Create Date: 2026-02-26 13:55:16.352552

"""

import sqlalchemy as sa
from alembic import op

revision = "048_multi_submissions_managed"
down_revision = "047_non_null_external_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "multiple_submissions_are_managed_by_service", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    op.create_check_constraint(
        op.f("ck_multiple_submissions_are_managed_by_service"),
        "collection",
        "multiple_submissions_are_managed_by_service = false OR allow_multiple_submissions = true",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_multiple_submissions_are_managed_by_service"), "collection", type_="check")
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("multiple_submissions_are_managed_by_service")
