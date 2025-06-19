"""Make GGIS number required

Revision ID: 008_make_ggis_number_required
Revises: 007_expression_eq_validation_key
Create Date: 2025-06-19 15:32:00.000000

"""

from alembic import op

revision = "008_make_ggis_number_required"
down_revision = "007_expression_eq_validation_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("ggis_number", nullable=False, existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("ggis_number", nullable=True, existing_nullable=False)
