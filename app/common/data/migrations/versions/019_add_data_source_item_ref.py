"""Add DataSourceItemReference table

Revision ID: 019_add_data_source_item_ref
Revises: 018_add_url_type
Create Date: 2025-07-16 08:25:37.365949

"""

import sqlalchemy as sa
from alembic import op

revision = "019_add_data_source_item_ref"
down_revision = "018_add_url_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_source_item_reference",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data_source_item_id", sa.Uuid(), nullable=False),
        sa.Column("expression_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_item_id"],
            ["data_source_item.id"],
            name=op.f("fk_data_source_item_reference_data_source_item_id_data_source_item"),
        ),
        sa.ForeignKeyConstraint(
            ["expression_id"], ["expression.id"], name=op.f("fk_data_source_item_reference_expression_id_expression")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source_item_reference")),
    )


def downgrade() -> None:
    op.drop_table("data_source_item_reference")
