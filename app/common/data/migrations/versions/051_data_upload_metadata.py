"""Add reference data upload metadata

Revision ID: 051_data_upload_metadata
Revises: 050_multiple_custom_expressions
Create Date: 2026-03-11 15:15:11.552081

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "051_data_upload_metadata"
down_revision = "050_multiple_custom_expressions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.add_column(sa.Column("file_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.execute(
        """
         UPDATE data_source
         SET file_metadata = '{}'::jsonb
         WHERE type != 'CUSTOM' AND file_metadata IS NULL
         """
    )

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_constraint("ck_data_source_non_custom_requires_name_grant_collection_and_schema", type_="check")
        batch_op.create_check_constraint(
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema_and_file_metadata",
            (
                "type = 'CUSTOM' OR "
                "(name IS NOT NULL AND grant_id IS NOT NULL AND collection_id IS NOT NULL "
                "AND schema IS NOT NULL AND file_metadata IS NOT NULL)"
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema_and_file_metadata", type_="check"
        )
        batch_op.drop_column("file_metadata")
        batch_op.create_check_constraint(
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema",
            (
                "type = 'CUSTOM' OR "
                "(name IS NOT NULL AND grant_id IS NOT NULL AND collection_id IS NOT NULL AND schema IS NOT NULL)"
            ),
        )
