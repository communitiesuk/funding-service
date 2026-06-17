from unittest.mock import patch

from flask import Flask

from app.common.data.types import RoleEnum
from app.common.helpers.feature_flags import (
    NewContextSourcesFeatureFlag,
    PreAwardGrantFeatureFlag,
    StaticFeatureFlag,
)


class TestFeatureFlag:
    def test_resolver(self) -> None:
        class AlwaysOn(StaticFeatureFlag):
            description = "Always on"
            resolver_description = "Always resolves to True"
            is_global = True

            @classmethod
            def resolve(cls) -> bool:
                return True

        class AlwaysOff(StaticFeatureFlag):
            description = "Always off"
            resolver_description = "Always resolves to False"
            is_global = True

            @classmethod
            def resolve(cls) -> bool:
                return False

        assert AlwaysOn().is_enabled is True
        assert AlwaysOff().is_enabled is False

    def test_bool(self) -> None:
        class AlwaysOn(StaticFeatureFlag):
            description = "Always on"
            resolver_description = "Always resolves to True"
            is_global = True

            @classmethod
            def resolve(cls) -> bool:
                return True

        class AlwaysOff(StaticFeatureFlag):
            description = "Always off"
            resolver_description = "Always resolves to False"
            is_global = True

            @classmethod
            def resolve(cls) -> bool:
                return False

        assert bool(AlwaysOn()) is True
        assert bool(AlwaysOff()) is False


class TestPreAwardGrantFeatureFlag:
    flag = PreAwardGrantFeatureFlag()

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


class TestNewContextSourcesFeatureFlag:
    flag = NewContextSourcesFeatureFlag()

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
