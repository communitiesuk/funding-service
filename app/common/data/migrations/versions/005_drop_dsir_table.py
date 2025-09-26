"""drop the data source item reference table; we're using the component reference table instead now

Revision ID: 005_drop_dsir_table
Revises: 004_migrate_data_source_refs
Create Date: 2025-09-25 16:49:47.087780

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_drop_dsir_table"
down_revision = "004_migrate_data_source_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("data_source_item_reference")


def downgrade() -> None:
    op.create_table(
        "data_source_item_reference",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at_utc",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("data_source_item_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("expression_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_item_id"],
            ["data_source_item.id"],
            name="fk_data_source_item_reference_data_source_item_id_data__c264",
        ),
        sa.ForeignKeyConstraint(
            ["expression_id"], ["expression.id"], name="fk_data_source_item_reference_expression_id_expression"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_source_item_reference"),
    )
