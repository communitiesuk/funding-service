"""Makes requires_certification non-nullable

Revision ID: 074_non_nullable_certification
Revises: 073_add_grant_slug
Create Date: 2026-08-03 09:47:57.442769

"""

import sqlalchemy as sa
from alembic import op

revision = "074_non_nullable_certification"
down_revision = "073_add_grant_slug"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.alter_column(
            "requires_certification", existing_type=sa.BOOLEAN(), nullable=False, server_default=sa.true()
        )
        batch_op.drop_constraint(op.f("ck_monitoring_certification_not_null"))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.alter_column("requires_certification", existing_type=sa.BOOLEAN(), nullable=True)
        batch_op.create_check_constraint(
            op.f("ck_monitoring_certification_not_null"),
            "requires_certification IS NOT NULL OR type != 'MONITORING_REPORT'",
        )
