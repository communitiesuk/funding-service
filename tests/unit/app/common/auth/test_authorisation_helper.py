from datetime import datetime

import pytest
from flask_login import AnonymousUserMixin
from pytz import utc

from app import AuthorisationHelper
from app.common.data.types import RoleEnum


class TestAuthorisationHelper:
    @pytest.mark.parametrize(
        "name, last_logged_in, expected",
        [
            ("John", datetime.now(utc), True),
            ("John", None, False),
            (None, datetime.now(utc), True),
            (None, None, False),
        ],
    )
    def test_has_logged_in(self, factories, name, last_logged_in, expected):
        user = factories.user.build(name=name, last_logged_in_at_utc=last_logged_in)
        assert AuthorisationHelper.has_logged_in(user) is expected

    @pytest.mark.parametrize(
        "role, has_grant_linked_to_role, expected",
        [
            (RoleEnum.ADMIN, False, True),
            (RoleEnum.ADMIN, True, False),
            (RoleEnum.MEMBER, True, False),
        ],
    )
    def test_is_platform_admin(self, factories, role, has_grant_linked_to_role, expected):
        user = factories.user.build()
        factories.user_role.build(user=user, role=role, has_grant=has_grant_linked_to_role)
        assert AuthorisationHelper.is_platform_admin(user) is expected

    def test_is_platform_admin_works_for_anonymous_user(self):
        assert AuthorisationHelper.is_platform_admin(AnonymousUserMixin()) is False

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, False),
        ],
    )
    def test_is_grant_admin_correct_grant(self, factories, role, expected):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant)
        assert AuthorisationHelper.is_grant_admin(user=user, grant_id=grant.id) is expected

    @pytest.mark.parametrize(
        "role",
        [
            (RoleEnum.ADMIN),
            (RoleEnum.MEMBER),
        ],
    )
    def test_is_grant_admin_incorrect_grant(self, factories, role):
        user = factories.user.build()
        grant1 = factories.grant.build()
        grant2 = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant1)
        assert AuthorisationHelper.is_grant_admin(user=user, grant_id=grant2.id) is False

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, False),
        ],
    )
    def test_is_grant_admin_for_grant_roles(self, factories, role, expected):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant)
        assert AuthorisationHelper.is_grant_admin(user=user, grant_id=grant.id) is expected

    @pytest.mark.parametrize(
        "role",
        [
            RoleEnum.ADMIN,
            RoleEnum.MEMBER,
        ],
    )
    def test_is_grant_member_true(self, factories, role):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=role, grant=grant)
        assert AuthorisationHelper.is_grant_member(user=user, grant_id=grant.id)

    @pytest.mark.parametrize("role", [RoleEnum.ADMIN, RoleEnum.MEMBER])
    def test_is_grant_member_false_member_of_different_grant(self, factories, role):
        user = factories.user.build()
        grants = factories.grant.build_batch(2)
        factories.user_role.build(user=user, role=role, grant=grants[0])
        assert AuthorisationHelper.is_grant_member(user=user, grant_id=grants[1].id) is False

    def test_is_grant_member_false_not_got_member_role(self, factories):
        user = factories.user.build()
        grant = factories.grant.build()
        assert AuthorisationHelper.is_grant_member(user=user, grant_id=grant.id) is False

    def test_is_grant_member_overriden_by_platform_admin(self, factories):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, role=RoleEnum.ADMIN, grant=None)
        assert AuthorisationHelper.is_grant_member(user=user, grant_id=grant.id) is True

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, True),
            ("S151_OFFICER", pytest.raises(ValueError)),
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
