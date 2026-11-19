from app.common.helpers.feature_flags import (
    StaticFeatureFlag,
)


class TestFeatureFlag:
    def test_resolver(self) -> None:
        class AlwaysOn(StaticFeatureFlag):
            description = "Always on"
            resolver_description = "Always resolves to True"
            uses_request_context = False

            @classmethod
            def resolve(cls) -> bool:
                return True

        class AlwaysOff(StaticFeatureFlag):
            description = "Always off"
            resolver_description = "Always resolves to False"
            uses_request_context = False

            @classmethod
            def resolve(cls) -> bool:
                return False

        assert AlwaysOn().is_enabled is True
        assert AlwaysOff().is_enabled is False

    def test_bool(self) -> None:
        class AlwaysOn(StaticFeatureFlag):
            description = "Always on"
            resolver_description = "Always resolves to True"
            uses_request_context = False

            @classmethod
            def resolve(cls) -> bool:
                return True

        class AlwaysOff(StaticFeatureFlag):
            description = "Always off"
            resolver_description = "Always resolves to False"
            uses_request_context = False

            @classmethod
            def resolve(cls) -> bool:
                return False

        assert bool(AlwaysOn()) is True
        assert bool(AlwaysOff()) is False
