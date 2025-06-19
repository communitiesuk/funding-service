"""Add azure_ad_subject_id to user model

Revision ID: 006_add_user_azure_ad_id
Revises: 005_userrole_unique_constraint
Create Date: 2025-06-18 15:27:48.117711

"""

import sqlalchemy as sa
from alembic import op

revision = "006_add_user_azure_ad_id"
down_revision = "005_userrole_unique_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("azure_ad_subject_id", sa.String(), nullable=True))
        batch_op.create_unique_constraint(batch_op.f("uq_user_azure_ad_subject_id"), ["azure_ad_subject_id"])


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_user_azure_ad_subject_id"), type_="unique")
        batch_op.drop_column("azure_ad_subject_id")
