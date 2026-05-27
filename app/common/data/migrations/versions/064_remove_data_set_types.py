"""Remove redundant data set types

Revision ID: 064_remove_data_set_types
Revises: 063_submission_status_not_null
Create Date: 2026-05-26 16:14:58.306592

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "064_remove_data_set_types"
down_revision = "063_submission_status_not_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema_and_file_metadata",
            type_="check",
        )

    # I've checked and we only have GRANT_RECIPIENT and CUSTOM data sources in deployed envs, so this is for safety/
    # local dev just in case people have STATIC or PROJECT_LEVEL data sources knocking around
    op.execute(
        "DELETE FROM data_source_item WHERE data_source_id IN (SELECT id FROM data_source WHERE type = 'STATIC')"
    )
    op.execute("DELETE FROM data_source WHERE type IN ('STATIC', 'PROJECT_LEVEL')")

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="data_source_type_enum",
        new_values=["CUSTOM", "GRANT_RECIPIENT"],
        affected_columns=[TableReference(table_schema="public", table_name="data_source", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("data_source", schema=None) as batch_op:
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
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema_and_file_metadata",
            type_="check",
        )

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="data_source_type_enum",
        new_values=["CUSTOM", "STATIC", "GRANT_RECIPIENT", "PROJECT_LEVEL"],
        affected_columns=[TableReference(table_schema="public", table_name="data_source", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema_and_file_metadata",
            (
                "type = 'CUSTOM' OR "
                "(name IS NOT NULL AND grant_id IS NOT NULL AND collection_id IS NOT NULL "
                "AND schema IS NOT NULL AND file_metadata IS NOT NULL)"
            ),
        )
