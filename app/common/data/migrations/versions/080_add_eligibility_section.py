"""Add is_eligibility_section column to form table
Drop collection_id unique constraint and add a new one that only applies to eligibility sections

Revision ID: 080_add_eligibility_section
Revises: 079_access_team_audit_event
Create Date: 2026-08-15 13:33:18.102919

"""

import sqlalchemy as sa
from alembic import op

revision = "080_add_eligibility_section"
down_revision = "079_access_team_audit_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_eligibility_section", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index(
            "uq_form_eligibility_collection",
            ["collection_id"],
            unique=True,
            postgresql_where=sa.text("is_eligibility_section IS true"),
        )

    op.drop_constraint("ck_grant_recipient_if_live", "submission", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_grant_recipient_if_live", "submission", "mode = 'PREVIEW' OR grant_recipient_id IS NOT NULL"
    )

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_form_eligibility_collection", postgresql_where=sa.text("is_eligibility_section IS true")
        )
        batch_op.drop_column("is_eligibility_section")
