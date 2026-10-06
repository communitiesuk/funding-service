"""Remove auto-granted test grant recipient roles for users who never tested

Revision ID: 091_remove_test_recipient_roles
Revises: 090_add_unclaimed_sub_constraint
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op

revision = "091_remove_test_recipient_roles"
down_revision = "090_add_unclaimed_sub_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delete grant-specific roles on TEST grant recipient organisations where the user has neither a
    # submission nor a submission event for that recipient
    op.execute(
        sa.text("""
            DELETE FROM user_role ur
            USING organisation o, grant_recipient gr
            WHERE ur.organisation_id = o.id
              AND ur.grant_id IS NOT NULL
              AND o.mode = 'TEST'
              AND o.can_manage_grants = false
              AND gr.organisation_id = ur.organisation_id
              AND gr.grant_id = ur.grant_id
              AND gr.mode = 'TEST'
              AND ('DATA_PROVIDER' = ANY(ur.permissions) OR 'CERTIFIER' = ANY(ur.permissions))
              AND NOT EXISTS (
                  SELECT 1 FROM submission s
                  WHERE s.grant_recipient_id = gr.id
                    AND s.created_by_id = ur.user_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM submission_event se
                  JOIN submission s2 ON s2.id = se.submission_id
                  WHERE s2.grant_recipient_id = gr.id
                    AND se.created_by_id = ur.user_id
              )
        """)
    )

    # One-off cleanup of the audit events that recorded the automatic test-recipient grants
    op.execute(
        sa.text("""
            DELETE FROM audit_event ae
            USING grant_recipient gr, organisation o
            WHERE ae.event_type = 'USER_MANAGEMENT'
              AND ae.data->>'action' = 'permissions_added'
              AND (ae.data->'permissions' @> '"data-provider"'::jsonb
                   OR ae.data->'permissions' @> '"certifier"'::jsonb)
              AND gr.id = (ae.data->>'grant_recipient_id')::uuid
              AND gr.organisation_id = o.id
              AND gr.mode = 'TEST'
              AND o.mode = 'TEST'
        """)
    )


def downgrade() -> None:
    # Deleted roles and audit events cannot be reconstructed
    pass
