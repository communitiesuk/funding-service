"""adds domain validator

Revision ID: 019_has_domain_validator
Revises: 018_add_url_type
Create Date: 2025-07-15 18:11:10.440547

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "019_has_domain_validator"
down_revision = "018_add_url_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "IS_YES", "IS_NO", "ANY_OF", "HAS_DOMAIN"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "IS_YES", "IS_NO", "ANY_OF"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )
