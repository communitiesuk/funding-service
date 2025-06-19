import pytest

from app import AuthorisationHelper
from app.common.data.types import RoleEnum


class TestAuthorisationHelper:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("John", True),
            (None, False),
        ],
    )
    def test_has_logged_in(self, factories, name, expected):
        user = factories.user.build(name=name)
        assert AuthorisationHelper.has_logged_in(user) is expected

    @pytest.mark.parametrize(
        "role, is_grant, expected",
        [
            (RoleEnum.ADMIN, False, True),
            (RoleEnum.ADMIN, True, False),
            (RoleEnum.MEMBER, True, False),
        ],
    )
    def test_is_platform_admin(self, factories, role, is_grant, expected):
        user = factories.user.build()
        grant = factories.grant.build() if is_grant else None
        factories.user_role.build(user=user, role=role, grant=grant)
        assert AuthorisationHelper.is_platform_admin(user) is expected

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, False),
        ],
    )
    def test_is_grant_admin(self, factories, role, expected):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant)
        assert AuthorisationHelper.is_grant_admin(user=user, grant_id=grant.id) is expected

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, False),
            (RoleEnum.MEMBER, True),
        ],
    )
    def test_is_grant_member(self, factories, role, expected):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant)
        assert AuthorisationHelper.is_grant_member(user=user, grant_id=grant.id) is expected

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, True),
            (RoleEnum.S151_OFFICER, pytest.raises(ValueError)),
        ],
    )
    def test_has_grant_role(self, factories, role, expected):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant)

        if isinstance(expected, bool):
            assert AuthorisationHelper.has_grant_role(user=user, grant_id=grant.id, role=role) is expected
        else:
            with expected:
                AuthorisationHelper.has_grant_role(user=user, grant_id=grant.id, role=role)
