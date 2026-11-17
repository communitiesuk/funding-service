"""Add grant onboarding status

Revision ID: 018_add_onboarding_status
Revises: 017_allow_org_members
Create Date: 2025-11-05 11:47:27.092354

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "018_add_onboarding_status"
down_revision = "017_allow_org_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="grantstatusenum",
        new_values=["DRAFT", "ONBOARDING", "LIVE"],
        affected_columns=[TableReference(table_schema="public", table_name="grant", column_name="status")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="grantstatusenum",
        new_values=["DRAFT", "LIVE"],
        affected_columns=[TableReference(table_schema="public", table_name="grant", column_name="status")],
        enum_values_to_rename=[],
    )
