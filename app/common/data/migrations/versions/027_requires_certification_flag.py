"""add requires certification flag

Revision ID: 027_requires_certification_flag
Revises: 026_require_member_permission
Create Date: 2025-11-19 13:56:21.544903

"""

import sqlalchemy as sa
from alembic import op

revision = "027_requires_certification_flag"
down_revision = "026_require_member_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("requires_certification", sa.Boolean(), nullable=True))

    op.execute("UPDATE collection SET requires_certification = true WHERE type = 'MONITORING_REPORT'")

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_monitoring_certification_not_null"),
            "requires_certification IS NOT NULL OR type != 'MONITORING_REPORT'",
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("requires_certification")
