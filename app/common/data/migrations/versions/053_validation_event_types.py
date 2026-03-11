"""Add validation submission event types

Revision ID: 053_validation_event_types
Revises: 052_collection_validation
Create Date: 2026-03-11 12:00:00.000000

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "053_validation_event_types"
down_revision = "052_collection_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_event_type_enum",
        new_values=[
            "FORM_RUNNER_FORM_COMPLETED",
            "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
            "FORM_RUNNER_FORM_RESET_BY_CERTIFIER",
            "FORM_RUNNER_FORM_RESET_BY_VALIDATOR",
            "SUBMISSION_SENT_FOR_CERTIFICATION",
            "SUBMISSION_DECLINED_BY_CERTIFIER",
            "SUBMISSION_APPROVED_BY_CERTIFIER",
            "SUBMISSION_SUBMITTED",
            "SUBMISSION_VALIDATED",
            "SUBMISSION_CHANGES_REQUESTED_BY_VALIDATOR",
            "SUBMISSION_VALIDATION_DECLINED",
        ],
        affected_columns=[
            TableReference(table_schema="public", table_name="submission_event", column_name="event_type")
        ],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_event_type_enum",
        new_values=[
            "FORM_RUNNER_FORM_COMPLETED",
            "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
            "FORM_RUNNER_FORM_RESET_BY_CERTIFIER",
            "SUBMISSION_SENT_FOR_CERTIFICATION",
            "SUBMISSION_DECLINED_BY_CERTIFIER",
            "SUBMISSION_APPROVED_BY_CERTIFIER",
            "SUBMISSION_SUBMITTED",
        ],
        affected_columns=[
            TableReference(table_schema="public", table_name="submission_event", column_name="event_type")
        ],
        enum_values_to_rename=[],
    )
