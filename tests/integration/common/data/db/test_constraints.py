import pytest
from sqlalchemy.exc import IntegrityError

from app.common.data.types import ExpressionType, ManagedExpressionsEnum, RoleEnum


class TestUserRoleConstraints:
    def test_member_role_not_platform(self, factories):
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(has_grant=False, has_organisation=False, role=RoleEnum.MEMBER)
        assert (
            'new row for relation "user_role" violates check constraint "ck_user_role_member_role_not_platform"'
            in error.value.args[0]
        )

    def test_unique_constraint_with_nulls(self, factories):
        user_role = factories.user_role.create(role=RoleEnum.ADMIN)
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(user_id=user_role.user_id, user=user_role.user, role=RoleEnum.ADMIN)
        assert 'duplicate key value violates unique constraint "uq_user_org_grant"' in error.value.args[0]


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
