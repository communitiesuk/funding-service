import pytest
from sqlalchemy.exc import IntegrityError

from app.common.data.types import RoleEnum


class TestUserRoleConstraints:
    def test_member_role_not_platform(self, factories):
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(has_grant=False, has_organisation=False, role=RoleEnum.MEMBER)
        assert (
            'new row for relation "user_role" violates check constraint "ck_user_role_member_role_not_platform"'
            in error.value.args[0]
        )

    @pytest.mark.parametrize("has_organisation, has_grant", [(True, True), (False, True)])
    def test_s151_officer_role_org_only(self, factories, has_organisation, has_grant):
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(
                has_organisation=has_organisation, has_grant=has_grant, role=RoleEnum.S151_OFFICER
            )
        assert (
            'new row for relation "user_role" violates check constraint "ck_user_role_s151_officer_role_org_only"'
            in error.value.args[0]
        )

    @pytest.mark.parametrize("has_organisation, has_grant", [(True, True), (True, False)])
    def test_assessor_role_grant_only(self, factories, has_organisation, has_grant):
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(has_organisation=has_organisation, has_grant=has_grant, role=RoleEnum.ASSESSOR)
        assert (
            'new row for relation "user_role" violates check constraint "ck_user_role_assessor_role_grant_only"'
            in error.value.args[0]
        )

    def test_unique_constraint_with_nulls(self, factories):
        user_role = factories.user_role.create(role=RoleEnum.ADMIN)
        with pytest.raises(IntegrityError) as error:
            factories.user_role.create(user_id=user_role.user_id, user=user_role.user, role=RoleEnum.ADMIN)
        assert 'duplicate key value violates unique constraint "uq_user_org_grant"' in error.value.args[0]
