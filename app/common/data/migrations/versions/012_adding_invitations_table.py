"""Adding invitations table, and last_logged_in_at_utc to user

Revision ID: 012_adding_invitations_table
Revises: 011_sync_role_enum
Create Date: 2025-06-26 13:37:11.014236

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012_adding_invitations_table"
down_revision = "011_sync_role_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=True),
        sa.Column("grant_id", sa.Uuid(), nullable=True),
        sa.Column("role", postgresql.ENUM(name="role_enum", create_type=False), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
        sa.Column("claimed_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["grant_id"], ["grant.id"], name=op.f("fk_invitation_grant_id_grant"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
            name=op.f("fk_invitation_organisation_id_organisation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_invitation_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitation")),
    )
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", postgresql.CITEXT(), nullable=True))
        batch_op.alter_column("user_id", existing_type=sa.UUID(), nullable=True)

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_logged_in_at_utc", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("last_logged_in_at_utc")

    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.drop_column("email")
        batch_op.alter_column("user_id", existing_type=sa.UUID(), nullable=False)

    op.drop_table("invitation")
