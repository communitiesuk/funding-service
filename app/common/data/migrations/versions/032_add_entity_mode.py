"""Add mode fields to organisation and grant_recipient

Revision ID: 032_test_modes
Revises: 031_submission_references
Create Date: 2025-12-11 15:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

revision = "032_test_modes"
down_revision = "031_submission_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE organisation_mode_enum AS ENUM ('LIVE', 'TEST')")
    op.execute("CREATE TYPE grant_recipient_mode_enum AS ENUM ('LIVE', 'TEST')")

    # Add mode column to organisation table
    op.add_column(
        "organisation",
        sa.Column(
            "mode", sa.Enum("LIVE", "TEST", name="organisation_mode_enum"), nullable=False, server_default="LIVE"
        ),
    )

    # Add mode column to grant_recipient table
    op.add_column(
        "grant_recipient",
        sa.Column(
            "mode", sa.Enum("LIVE", "TEST", name="grant_recipient_mode_enum"), nullable=False, server_default="LIVE"
        ),
    )

    op.sync_enum_values(  # type: ignore[attr-defined]
        enum_schema="public",
        enum_name="submission_mode_enum",
        new_values=["TEST", "PREVIEW", "LIVE"],
        affected_columns=[TableReference(table_schema="public", table_name="submission", column_name="mode")],
        enum_values_to_rename=[],
    )

    op.create_check_constraint(
        "ck_grant_recipient_if_live", "submission", "mode = 'PREVIEW' OR grant_recipient_id IS NOT NULL"
    )


def downgrade() -> None:
    # Remove mode columns
    op.drop_column("grant_recipient", "mode")
    op.drop_column("organisation", "mode")

    # Drop enum types
    op.execute("DROP TYPE grant_recipient_mode_enum")
    op.execute("DROP TYPE organisation_mode_enum")

    # Remove 'preview' from submission_mode_enum
    op.sync_enum_values(  # type: ignore[attr-defined]
        enum_schema="public",
        enum_name="submission_mode_enum",
        new_values=["TEST", "LIVE"],
        affected_columns=[TableReference(table_schema="public", table_name="submission", column_name="mode")],
        enum_values_to_rename=[],
    )

    # Restore old constraint
    op.create_check_constraint(
        "ck_grant_recipient_if_live", "submission", "mode = 'TEST' OR grant_recipient_id IS NOT NULL"
    )
