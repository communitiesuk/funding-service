"""Makes the user_role unique constraint allow nulls to be not distinct

Revision ID: 003_nulls_not_distinct_user_role
Revises: 002_add_collection
Create Date: 2025-05-21 14:31:53.192474

"""

from alembic import op

revision = "003_nulls_not_distinct_user_role"
down_revision = "002_add_collection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_org_grant_role", type_="unique")
        batch_op.create_unique_constraint(
            "uq_user_org_grant_role",
            ["user_id", "organisation_id", "grant_id", "role"],
            postgresql_nulls_not_distinct=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_org_grant_role", type_="unique")
        batch_op.create_unique_constraint("uq_user_org_grant_role", ["user_id", "organisation_id", "grant_id", "role"])
