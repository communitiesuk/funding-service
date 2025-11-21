"""require member permission

Revision ID: 026_require_member_permission
Revises: 025_awaiting_sign_off_status
Create Date: 2025-11-20 00:00:00.000000

"""

from alembic import op

revision = "026_require_member_permission"
down_revision = "025_awaiting_sign_off_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_non_admin_permissions_require_org"), type_="check")
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_invitation_non_admin_permissions_require_org"), type_="check")

    op.execute(
        """
        UPDATE user_role
        SET permissions = array_append(permissions, 'MEMBER')
        WHERE NOT ('MEMBER' = ANY(permissions))
        """
    )
    op.execute(
        """
        UPDATE invitation
        SET permissions = array_append(permissions, 'MEMBER')
        WHERE NOT ('MEMBER' = ANY(permissions))
        """
    )

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_user_role_non_admin_permissions_require_org"),
            "('CERTIFIER' != ALL(permissions) AND 'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_permission_required"),
            "'MEMBER' = ANY(permissions)",
        )

    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_invitation_non_admin_permissions_require_org"),
            "('CERTIFIER' != ALL(permissions) AND 'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_invitation_member_permission_required"),
            "'MEMBER' = ANY(permissions)",
        )


def downgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_invitation_non_admin_permissions_require_org"), type_="check")
        batch_op.drop_constraint(op.f("ck_invitation_member_permission_required"), type_="check")

    op.execute(
        """
        UPDATE invitation
        SET permissions = array_remove(permissions, 'MEMBER')
        WHERE 'MEMBER' = ANY(permissions) AND organisation_id IS NULL
        """
    )

    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_invitation_non_admin_permissions_require_org"),
            (
                "('MEMBER' != ALL(permissions) AND 'CERTIFIER' != ALL(permissions) AND "
                "'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL"
            ),
        )

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_non_admin_permissions_require_org"), type_="check")
        batch_op.drop_constraint(op.f("ck_user_role_member_permission_required"), type_="check")

    op.execute(
        """
        UPDATE user_role
        SET permissions = array_remove(permissions, 'MEMBER')
        WHERE 'MEMBER' = ANY(permissions) AND organisation_id IS NULL
        """
    )

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_user_role_non_admin_permissions_require_org"),
            (
                "('MEMBER' != ALL(permissions) AND 'CERTIFIER' != ALL(permissions) AND "
                "'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL"
            ),
        )
