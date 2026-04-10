from unittest.mock import patch

import pytest
from flask import Flask

from app.common.helpers.feature_flags import PRE_AWARD_FEATURES, FeatureFlag


class TestFeatureFlag:
    def test_resolver(self) -> None:
        flag = FeatureFlag(description="Always on", resolver=lambda: True)
        assert flag.is_enabled is True

        flag = FeatureFlag(description="Always off", resolver=lambda: False)
        assert flag.is_enabled is False

    def test_bool(self) -> None:
        assert bool(FeatureFlag(description="Always on", resolver=lambda: True)) is True
        assert bool(FeatureFlag(description="Always off", resolver=lambda: False)) is False


class TestPreAwardFeaturesFlag:
    def test_enabled(self, app: Flask, factories) -> None:
        grant = factories.grant.build(allow_pre_award=True)

        with app.test_request_context(f"/deliver/grant/{grant.id}/reports"):
            with patch("app.common.helpers.feature_flags.get_grant", return_value=grant):
                assert PRE_AWARD_FEATURES.is_enabled is True

    def test_disabled(self, app: Flask, factories) -> None:
        grant = factories.grant.build(allow_pre_award=False)

        with app.test_request_context(f"/deliver/grant/{grant.id}/reports"):
            with patch("app.common.helpers.feature_flags.get_grant", return_value=grant):
                assert PRE_AWARD_FEATURES.is_enabled is False

    def test_raises(self, app: Flask) -> None:
        with app.test_request_context("/"):
            with pytest.raises(ValueError, match="grant_id required"):
                assert PRE_AWARD_FEATURES.is_enabled
