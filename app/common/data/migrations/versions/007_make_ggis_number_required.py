"""Make GGIS number required

Revision ID: 007_make_ggis_number_required
Revises: 006_add_user_azure_ad_id
Create Date: 2025-06-19 15:32:00.000000

"""

from alembic import op

revision = "007_make_ggis_number_required"
down_revision = "006_add_user_azure_ad_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("ggis_number", nullable=False, existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("ggis_number", nullable=True, existing_nullable=False)
