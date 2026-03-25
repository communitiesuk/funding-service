"""Add assessment submission event types, requires_scoring column, and data_options

Revision ID: 055_assessment_event_types
Revises: 054_public_collection
Create Date: 2026-03-20 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql

revision = "055_assessment_event_types"
down_revision = "054_public_collection"
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
            "SECTION_SCORED",
            "SECTION_COMMENT_ADDED",
        ],
        affected_columns=[
            TableReference(table_schema="public", table_name="submission_event", column_name="event_type")
        ],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("requires_scoring", sa.Boolean(), server_default=sa.text("false"), nullable=False)
        )
        batch_op.add_column(
            sa.Column("data_options", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("data_options")
        batch_op.drop_column("requires_scoring")

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
