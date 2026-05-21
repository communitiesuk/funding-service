from unittest.mock import patch

from flask import Flask

from app.common.data.types import RoleEnum
from app.common.helpers.feature_flags import (
    FeatureFlag,
    _check_grant_allows_pre_award,
    _check_user_is_platform_member,
)


class TestFeatureFlag:
    def test_resolver(self) -> None:
        flag = FeatureFlag(description="Always on", resolver=lambda: True)
        assert flag.is_enabled is True

        flag = FeatureFlag(description="Always off", resolver=lambda: False)
        assert flag.is_enabled is False

    def test_bool(self) -> None:
        assert bool(FeatureFlag(description="Always on", resolver=lambda: True)) is True
        assert bool(FeatureFlag(description="Always off", resolver=lambda: False)) is False


class TestCheckGrantAllowsPreAward:
    flag = FeatureFlag(description="Pre award resolver", resolver=_check_grant_allows_pre_award)

    def test_enabled(self, app: Flask, factories) -> None:
        grant = factories.grant.build(allow_pre_award=True)

        with app.test_request_context(f"/deliver/grant/{grant.id}/reports"):
            with patch("app.common.helpers.feature_flags.get_grant", return_value=grant):
                assert self.flag.is_enabled is True

    def test_disabled(self, app: Flask, factories) -> None:
        grant = factories.grant.build(allow_pre_award=False)

        with app.test_request_context(f"/deliver/grant/{grant.id}/reports"):
            with patch("app.common.helpers.feature_flags.get_grant", return_value=grant):
                assert self.flag.is_enabled is False

    def test_disabled_without_grant_id(self, app: Flask, factories) -> None:
        grant = factories.grant.build(allow_pre_award=True)
        with app.test_request_context("/"):
            with patch("app.common.helpers.feature_flags.get_grant", return_value=grant):
                assert self.flag.is_enabled is False


class TestCheckUserIsPlatformMember:
    flag = FeatureFlag(description="User is platform member resolver", resolver=_check_user_is_platform_member)

    def test_enabled(self, app: Flask, factories) -> None:
        user = factories.user.build()
        factories.user_role.build(user=user, organisation=None, grant=None, permissions=[RoleEnum.MEMBER])

        with app.test_request_context("/"):
            with patch("app.common.helpers.feature_flags.get_current_user", return_value=user):
                assert self.flag.is_enabled is True

    def test_disabled(self, app: Flask, factories) -> None:
        user = factories.user.build()
        with app.test_request_context("/"):
            with patch("app.common.helpers.feature_flags.get_current_user", return_value=user):
                assert self.flag.is_enabled is False
