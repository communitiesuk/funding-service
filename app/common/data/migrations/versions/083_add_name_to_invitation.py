"""Add the invitee's name to invitations

Revision ID: 083_add_name_to_invitation
Revises: 082_add_eligibility_type_expr
Create Date: 2026-09-02 10:09:07.983297

"""

import sqlalchemy as sa
from alembic import op

revision = "083_add_name_to_invitation"
down_revision = "082_add_eligibility_type_expr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.drop_column("name")
