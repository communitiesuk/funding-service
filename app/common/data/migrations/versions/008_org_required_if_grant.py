"""add org_required_if_grant constraint

Revision ID: 008_org_required_if_grant
Revises: 007_add_grant_to_org_fk
Create Date: 2025-10-18 14:08:44.658679

"""

from alembic import op

revision = "008_org_required_if_grant"
down_revision = "007_add_grant_to_org_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Populate organisation_id for any user_role entries that have a grant_id but no organisation_id
    # by joining with the grant table
    op.execute(
        sqltext="""
        UPDATE user_role
        SET organisation_id = "grant".organisation_id
        FROM"grant"
        WHERE user_role.grant_id = "grant".id
        AND user_role.organisation_id IS NULL
        AND "grant".organisation_id IS NOT NULL
        """
    )

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "org_required_if_grant",
            "(organisation_id IS NULL AND grant_id IS NULL) or (organisation_id IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint("org_required_if_grant", type_="check")
