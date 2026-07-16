"""Add assessment_status column to submission table

Revision ID: 070_add_assessment_status_col
Revises: 069_changes_req_sub_status
Create Date: 2026-07-16 19:21:06.012052

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql

revision = "070_add_assessment_status_col"
down_revision = "069_changes_req_sub_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("NOT_STARTED", "MARKED_AS_APPROVED", "MARKED_AS_REJECTED", name="submission_assessment_status_enum").create(
        op.get_bind()
    )
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "assessment_status",
                postgresql.ENUM(
                    "NOT_STARTED",
                    "MARKED_AS_APPROVED",
                    "MARKED_AS_REJECTED",
                    name="submission_assessment_status_enum",
                    create_type=False,
                ),
                nullable=False,
                server_default="NOT_STARTED",
            )
        )

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
            "SUBMISSION_CHANGES_REQUESTED",
            "ASSESSOR_MARKED_AS_APPROVED",
            "ASSESSOR_MARKED_AS_REJECTED",
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
            "SUBMISSION_REOPENED",
            "SUBMISSION_CHANGES_REQUESTED",
        ],
        affected_columns=[
            TableReference(table_schema="public", table_name="submission_event", column_name="event_type")
        ],
        enum_values_to_rename=[],
    )
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_column("assessment_status")

    sa.Enum("NOT_STARTED", "MARKED_AS_APPROVED", "MARKED_AS_REJECTED", name="submission_assessment_status_enum").drop(
        op.get_bind()
    )
