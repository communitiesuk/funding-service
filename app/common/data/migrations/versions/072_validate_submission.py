"""Add submission assessment status, assessor events, and the validate submission collection setting

Revision ID: 072_validate_submission
Revises: 071_public_sign_up_page
Create Date: 2026-07-14 23:13:25.740520

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql

revision = "072_validate_submission"
down_revision = "071_public_sign_up_page"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("NOT_STARTED", "MARKED_AS_APPROVED", "MARKED_AS_REJECTED", name="submission_assessment_status_enum").create(
        op.get_bind()
    )

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("allow_validate_submission", sa.Boolean(), nullable=False, server_default=sa.false())
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
                server_default="NOT_STARTED",
                nullable=False,
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
            "ASSESSMENT_DECISION_REVISED",
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

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("allow_validate_submission")

    sa.Enum("NOT_STARTED", "MARKED_AS_APPROVED", "MARKED_AS_REJECTED", name="submission_assessment_status_enum").drop(
        op.get_bind()
    )
