"""add grant status

Revision ID: 009_add_grant_status
Revises: 008_org_required_if_grant
Create Date: 2025-10-23 19:31:11.280150

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_add_grant_status"
down_revision = "008_org_required_if_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("DRAFT", "LIVE", name="grantstatusenum").create(op.get_bind())
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status", postgresql.ENUM("DRAFT", "LIVE", name="grantstatusenum", create_type=False), nullable=True
            )
        )

    op.execute("""UPDATE "grant" SET status='DRAFT'""")

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("status", existing_nullable=True, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_column("status")

    sa.Enum("DRAFT", "LIVE", name="grantstatusenum").drop(op.get_bind())
