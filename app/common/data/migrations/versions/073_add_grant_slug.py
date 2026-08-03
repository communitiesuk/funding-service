"""Add Grant slug column and backfill value

Revision ID: 073_add_grant_slug
Revises: 072_add_allow_validation_col
Create Date: 2026-07-29 19:20:33.257320

"""

import sqlalchemy as sa
from alembic import op

revision = "073_add_grant_slug"
down_revision = "072_add_allow_validation_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(), nullable=True))

    op.execute(
        r"""
        UPDATE "grant"
        SET slug = regexp_replace(
            trim(lower(regexp_replace(name, '[^a-zA-Z0-9\s-]', '', 'g'))),
            '[\s-]+', '-', 'g'
        )
        """
    )

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_column("slug")
