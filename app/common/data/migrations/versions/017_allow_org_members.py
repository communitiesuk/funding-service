"""allow org members

Revision ID: 017_allow_org_members
Revises: 016_remove_collection_versioning
Create Date: 2025-11-04 11:46:13.734360

"""

from alembic import op

revision = "017_allow_org_members"
down_revision = "016_remove_collection_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_member_role_not_platform"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_role_not_platform"),
            "role != 'MEMBER' OR organisation_id IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_member_role_not_platform"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_role_not_platform"),
            "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
        )
