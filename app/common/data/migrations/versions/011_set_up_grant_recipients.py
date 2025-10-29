"""set up grant recipients

Revision ID: 011_set_up_grant_recipients
Revises: 010_add_org_columns
Create Date: 2025-10-28 16:52:56.386412

"""

import sqlalchemy as sa
from alembic import op

revision = "011_set_up_grant_recipients"
down_revision = "010_add_org_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grant_recipient",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("grant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["grant_id"], ["grant.id"], name=op.f("fk_grant_recipient_grant_id_grant")),
        sa.ForeignKeyConstraint(
            ["organisation_id"], ["organisation.id"], name=op.f("fk_grant_recipient_organisation_id_organisation")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grant_recipient")),
    )


def downgrade() -> None:
    op.drop_table("grant_recipient")
