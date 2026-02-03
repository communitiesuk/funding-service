"""Grant recipient status

Revision ID: 050_grant_recipient_status
Revises: 049_collection_types
Create Date: 2026-02-03 12:51:36.505252

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "050_grant_recipient_status"
down_revision = "049_collection_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("APPLYING", "ALLOCATED", "AWARDED", "DECLINED", name="grantrecipientstatus").create(op.get_bind())
    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                postgresql.ENUM(
                    "APPLYING", "ALLOCATED", "AWARDED", "DECLINED", name="grantrecipientstatus", create_type=False
                ),
                server_default="ALLOCATED",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.drop_column("status")

    sa.Enum("APPLYING", "ALLOCATED", "AWARDED", "DECLINED", name="grantrecipientstatus").drop(op.get_bind())
