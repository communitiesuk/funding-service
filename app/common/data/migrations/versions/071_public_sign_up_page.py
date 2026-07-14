"""Adds a slug to grants and a prospectus to collections, for the public sign up page

Revision ID: 071_public_sign_up_page
Revises: 070_trusted_domains
Create Date: 2026-07-14 18:02:11.000000

"""

import sqlalchemy as sa
from alembic import op

from app.common.utils import slugify

revision = "071_public_sign_up_page"
down_revision = "070_trusted_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(), nullable=True))

    connection = op.get_bind()
    grants = connection.execute(sa.text('SELECT id, name FROM "grant"')).fetchall()
    for grant_id, name in grants:
        connection.execute(
            sa.text('UPDATE "grant" SET slug = :slug WHERE id = :id'), {"slug": slugify(name), "id": grant_id}
        )

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("slug", nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_grant_slug"), ["slug"])

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prospectus_markdown", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("prospectus_markdown")

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_grant_slug"), type_="unique")
        batch_op.drop_column("slug")
