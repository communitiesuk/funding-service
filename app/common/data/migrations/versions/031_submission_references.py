"""add grant codes and submission references

Revision ID: 031_submission_references
Revises: 030_submission_workflow
Create Date: 2025-12-10 09:17:07.234536

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "031_submission_references"
down_revision = "030_submission_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code", postgresql.CITEXT(), nullable=True))

    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reference", postgresql.CITEXT(), nullable=True))

    op.execute(
        """
        UPDATE "grant"
        SET code = UPPER(
                         REGEXP_REPLACE(
                             REGEXP_REPLACE("grant".name, '(\\w)\\w*\\s*', '\\1', 'g'),
                             '[^A-Za-z]', '', 'g'
                         )
                   )
        WHERE code IS NULL
        """
    )

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("code", existing_nullable=True, nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_grant_code"), ["code"])

    # tiny risk of non-unique reference generation, but so small as to be ignorable for us
    op.execute(
        """
        UPDATE submission s
        SET reference = subq.new_reference
        FROM (
            SELECT
                s.id,
                g.code || '-R' ||
                STRING_AGG(
                    SUBSTRING('234679CDFGHJKLMNPQRTVWXYZ' FROM floor(random() * 25)::int + 1 FOR 1),
                    ''
                ) AS new_reference
            FROM
                submission s
                INNER JOIN collection c ON s.collection_id = c.id
                INNER JOIN "grant" g ON c.grant_id = g.id
            CROSS JOIN generate_series(1, 6) -- Generate 6 random characters
            GROUP BY s.id, g.code
        ) subq
        WHERE s.id = subq.id;
        """
    )

    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.alter_column("reference", existing_nullable=True, nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_submission_reference"), ["reference"])


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_submission_reference"), type_="unique")
        batch_op.drop_column("reference")

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_grant_code"), type_="unique")
        batch_op.drop_column("code")
