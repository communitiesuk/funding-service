"""Remove static data from submission events

Revision ID: 035_remove_static_event_data
Revises: 034_add_audit_events
Create Date: 2025-12-29

"""

from alembic import op

revision = "035_remove_static_event_data"
down_revision = "034_add_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE submission_event
        SET data = data - 'is_completed'
        WHERE event_type IN
        ('FORM_RUNNER_FORM_COMPLETED', 'FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS', 'FORM_RUNNER_FORM_RESET_BY_CERTIFIER')
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data - 'is_awaiting_sign_off' - 'is_approved'
        WHERE event_type IN (
            'SUBMISSION_SENT_FOR_CERTIFICATION',
            'SUBMISSION_DECLINED_BY_CERTIFIER',
            'SUBMISSION_APPROVED_BY_CERTIFIER'
        )
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data - 'is_submitted'
        WHERE event_type = 'SUBMISSION_SUBMITTED'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE submission_event
        SET data = data || '{"is_completed": true}'::jsonb
        WHERE event_type = 'FORM_RUNNER_FORM_COMPLETED'
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data || '{"is_completed": false}'::jsonb
        WHERE event_type IN ('FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS', 'FORM_RUNNER_FORM_RESET_BY_CERTIFIER')
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data || '{"is_awaiting_sign_off": true, "is_approved": false}'::jsonb
        WHERE event_type = 'SUBMISSION_SENT_FOR_CERTIFICATION'
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data || '{"is_awaiting_sign_off": false, "is_approved": false}'::jsonb
        WHERE event_type = 'SUBMISSION_DECLINED_BY_CERTIFIER'
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data || '{"is_awaiting_sign_off": false, "is_approved": true}'::jsonb
        WHERE event_type = 'SUBMISSION_APPROVED_BY_CERTIFIER'
        """
    )
    op.execute(
        """
        UPDATE submission_event
        SET data = data || '{"is_submitted": true}'::jsonb
        WHERE event_type = 'SUBMISSION_SUBMITTED'
        """
    )
