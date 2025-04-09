"""Add user and magic_link tables

Revision ID: 004_user_and_magic_links
Revises: 003_make_grant_name_citext
Create Date: 2025-04-09 15:39:03.617536

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_user_and_magic_links"
down_revision = "003_make_grant_name_citext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )
    op.create_table(
        "magic_link",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("redirect_to_path", sa.String(), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
        sa.Column("claimed_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_magic_link_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_magic_link")),
        sa.UniqueConstraint("code", name=op.f("uq_magic_link_code")),
    )
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_magic_link_code"), ["code"], unique=True, postgresql_where="claimed_at_utc IS NOT NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_magic_link_code"), postgresql_where="claimed_at_utc IS NOT NULL")

    op.drop_table("magic_link")
    op.drop_table("user")
