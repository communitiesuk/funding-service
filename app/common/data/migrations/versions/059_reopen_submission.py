"""Reopen submission event

Revision ID: 059_reopen_submission
Revises: 058_drop_legacy_question_id
Create Date: 2025-11-26 02:01:20.319522

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "059_reopen_submission"
down_revision = "058_drop_legacy_question_id"
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
            "SUBMISSION_SENT_FOR_CERTIFICATION",
            "SUBMISSION_DECLINED_BY_CERTIFIER",
            "SUBMISSION_APPROVED_BY_CERTIFIER",
            "SUBMISSION_SUBMITTED",
            "SUBMISSION_REOPENED",
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
