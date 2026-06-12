"""add grant recipient status

Revision ID: 065_add_grant_recipient_status
Revises: 064_remove_data_set_types
Create Date: 2026-06-12 12:34:31.181762

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "065_add_grant_recipient_status"
down_revision = "064_remove_data_set_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("APPLYING", "ALLOCATED", "AWARDED", name="grantrecipientstatusenum").create(op.get_bind())
    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                postgresql.ENUM("APPLYING", "ALLOCATED", "AWARDED", name="grantrecipientstatusenum", create_type=False),
                nullable=True,
            )
        )

    op.execute("UPDATE grant_recipient SET status = 'AWARDED'")

    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.alter_column("status", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.drop_column("status")

    sa.Enum("APPLYING", "ALLOCATED", "AWARDED", name="grantrecipientstatusenum").drop(op.get_bind())
