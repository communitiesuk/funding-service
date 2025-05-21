import pytest
from sqlalchemy.exc import IntegrityError

from app.common.data.models import RoleEnum


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
