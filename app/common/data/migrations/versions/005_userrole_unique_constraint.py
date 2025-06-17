"""change unique constraint on user_role table

Revision ID: 005_userrole_unique_constraint
Revises: 004_expressions
Create Date: 2025-06-17 21:01:11.235166

"""

from alembic import op

revision = "005_userrole_unique_constraint"
down_revision = "004_expressions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_org_grant_role", type_="unique")
        batch_op.create_unique_constraint(
            "uq_user_org_grant", ["user_id", "organisation_id", "grant_id"], postgresql_nulls_not_distinct=True
        )


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_org_grant", type_="unique")
        batch_op.create_unique_constraint(
            "uq_user_org_grant_role",
            ["user_id", "organisation_id", "grant_id", "role"],
            postgresql_nulls_not_distinct=True,
        )
