import pytest
from sqlalchemy.exc import IntegrityError

from app.common.data.types import ExpressionType, ManagedExpressionsEnum, RoleEnum


class TestUserRoleConstraints:
    def test_member_role_not_platform(self, factories):
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(has_grant=False, has_organisation=False, permissions=[RoleEnum.MEMBER])
        assert (
            'new row for relation "user_role" violates check constraint '
            '"ck_user_role_non_admin_permissions_require_org"'
        ) in error.value.args[0]

    def test_unique_constraint_with_nulls(self, factories):
        user_role = factories.user_role.create(permissions=[RoleEnum.ADMIN])
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(user_id=user_role.user_id, user=user_role.user, permissions=[RoleEnum.ADMIN])
        assert 'duplicate key value violates unique constraint "uq_user_org_grant"' in error.value.args[0]

    def test_grant_id_required_if_organisation_id(self, factories):
        grant = factories.grant.create()
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(
                permissions=[RoleEnum.ADMIN], organisation=None, organisation_id=None, grant=grant
            )
        assert (
            'new row for relation "user_role" violates check constraint "ck_user_role_org_required_if_grant"'
            in error.value.args[0]
        )


class TestExpressionConstraints:
    def test_cannot_add_two_of_the_same_kind_of_validation_to_a_question(self, factories):
        user = factories.user.create()
        q = factories.question.create()
        factories.expression.create(
            question=q,
            created_by=user,
            type_=ExpressionType.VALIDATION,
            statement="",
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
        )

        with pytest.raises(IntegrityError):
            factories.expression.create(
                question=q,
                created_by=user,
                type_=ExpressionType.VALIDATION,
                statement="",
                managed_name=ManagedExpressionsEnum.GREATER_THAN,
            )
