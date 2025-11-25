"""Submission events v2

Revision ID: 029_submission_events_v2
Revises: 028_add_conditions_operator
Create Date: 2025-11-25 12:39:45.888152

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "029_submission_events_v2"
down_revision = "028_add_conditions_operator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum(
        "FORM_RUNNER_FORM_COMPLETED",
        "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
        "SUBMISSION_SENT_FOR_CERTIFICATION",
        "SUBMISSION_SUBMITTED",
        name="submission_event_type_enum",
    ).create(op.get_bind())
    with op.batch_alter_table("submission_event", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "event_type",
                postgresql.ENUM(
                    "FORM_RUNNER_FORM_COMPLETED",
                    "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
                    "SUBMISSION_SENT_FOR_CERTIFICATION",
                    "SUBMISSION_SUBMITTED",
                    name="submission_event_type_enum",
                    create_type=False,
                ),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("target_key", sa.Uuid(), nullable=True))

        batch_op.add_column(
            sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False)
        )

    op.execute(
        sa.text("""
        UPDATE submission_event SET
                target_key = coalesce(submission_event.form_id, submission_event.submission_id),
                event_type = submission_event.key::TEXT::submission_event_type_enum
        """)
    )

    with op.batch_alter_table("submission_event", schema=None) as batch_op:
        batch_op.alter_column("target_key", nullable=False)
        batch_op.alter_column("event_type", nullable=False)
        batch_op.drop_constraint("fk_submission_event_form_id_form", type_="foreignkey")
        batch_op.drop_column("key")
        batch_op.drop_column("form_id")

    sa.Enum(
        "FORM_RUNNER_FORM_COMPLETED",
        "SUBMISSION_SENT_FOR_CERTIFICATION",
        "SUBMISSION_SUBMITTED",
        name="submission_event_key_enum",
    ).drop(op.get_bind())


def downgrade() -> None:
    sa.Enum(
        "FORM_RUNNER_FORM_COMPLETED",
        "SUBMISSION_SENT_FOR_CERTIFICATION",
        "SUBMISSION_SUBMITTED",
        name="submission_event_key_enum",
    ).create(op.get_bind())
    with op.batch_alter_table("submission_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("form_id", sa.UUID(), autoincrement=False, nullable=True))
        batch_op.add_column(
            sa.Column(
                "key",
                postgresql.ENUM(
                    "FORM_RUNNER_FORM_COMPLETED",
                    "SUBMISSION_SENT_FOR_CERTIFICATION",
                    "SUBMISSION_SUBMITTED",
                    name="submission_event_key_enum",
                    create_type=False,
                ),
                autoincrement=False,
                nullable=True,
            )
        )
        batch_op.create_foreign_key("fk_submission_event_form_id_form", "form", ["form_id"], ["id"])
        batch_op.drop_column("data")

    op.execute(
        sa.text("""
        UPDATE submission_event SET form_id = submission_event.target_key
        WHERE submission_event.event_type = 'FORM_RUNNER_FORM_COMPLETED'
        """)
    )
    op.execute(
        sa.text("""
        UPDATE submission_event SET key = submission_event.event_type::TEXT::submission_event_key_enum
        """)
    )

    with op.batch_alter_table("submission_event", schema=None) as batch_op:
        batch_op.alter_column("key", nullable=False)
        batch_op.drop_column("target_key")
        batch_op.drop_column("event_type")

    sa.Enum(
        "FORM_RUNNER_FORM_COMPLETED",
        "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
        "SUBMISSION_SENT_FOR_CERTIFICATION",
        "SUBMISSION_SUBMITTED",
        name="submission_event_type_enum",
    ).drop(op.get_bind())
