"""Renames INTEGER to NUMBER in question_data_type_enum
Also makes data_options NOT NULL

Revision ID: 037_sync_question_type_enum
Revises: 036_add_question_data_options
Create Date: 2026-01-26 14:32:15.081277

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql

revision = "037_sync_question_type_enum"
down_revision = "036_add_question_data_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=[
            "TEXT_SINGLE_LINE",
            "TEXT_MULTI_LINE",
            "EMAIL",
            "URL",
            "NUMBER",
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[("INTEGER", "NUMBER")],
    )
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column(
            "data_options",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            existing_server_default=sa.text("'{}'::jsonb"),
        )
    # Repeating this from previous migration to catch any questions created mid-deploy of the previous PR
    op.execute(
        sa.text("""
                UPDATE component
                SET data_options = '{"allow_decimals"\\:false}'
                WHERE data_type = 'NUMBER'
                """)
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=[
            "TEXT_SINGLE_LINE",
            "TEXT_MULTI_LINE",
            "EMAIL",
            "URL",
            "INTEGER",
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[("NUMBER", "INTEGER")],
    )
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column(
            "data_options",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            existing_server_default=sa.text("'{}'::jsonb"),
        )
