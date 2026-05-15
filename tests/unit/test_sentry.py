import pytest

from app.common.data.types import TraceLevelEnum
from app.common.helpers.request_tracing import REQUEST_TRACING_COOKIE_NAME, encode_levels
from app.sentry import profiles_sampler, traces_sampler


def _cookie_environ(secret: str, levels: list[TraceLevelEnum], path_info: str = "/anything") -> dict[str, str]:
    token = encode_levels(levels, secret)
    return {"PATH_INFO": path_info, "HTTP_COOKIE": f"{REQUEST_TRACING_COOKIE_NAME}={token}"}


class TestSentry:
    class TestTracesSampler:
        def test_healthcheck_is_never_sampled(self, app):
            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/healthcheck"}}) == 0

        def test_default_sample_rate_when_no_environ(self, app):
            assert traces_sampler({}) == 0.02

        def test_raises_when_secret_key_not_configured(self, app, monkeypatch):
            import app.sentry as sentry_module

            monkeypatch.setattr(sentry_module, "_secret_key", None)
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.TRACE])
            with pytest.raises(ValueError, match="Flask application secret key not configured for sentry"):
                traces_sampler({"wsgi_environ": wsgi_environ})

        def test_default_sample_rate_when_cookie_absent(self, app):
            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/anything"}}) == 0.02

        def test_default_sample_rate_when_cookie_signed_with_wrong_secret(self, app):
            wsgi_environ = _cookie_environ("not-the-secret", [TraceLevelEnum.TRACE])
            assert traces_sampler({"wsgi_environ": wsgi_environ}) == 0.02

        def test_default_sample_rate_when_cookie_only_has_profile_level(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.PROFILE])
            assert traces_sampler({"wsgi_environ": wsgi_environ}) == 0.02

        def test_default_sample_rate_when_cookie_only_has_debug_logging_level(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.DEBUG_LOGGING])
            assert traces_sampler({"wsgi_environ": wsgi_environ}) == 0.02

        def test_force_sampled_when_cookie_has_trace_level(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.TRACE])
            assert traces_sampler({"wsgi_environ": wsgi_environ}) == 1.0

        def test_force_sampled_when_cookie_has_all_levels(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], list(TraceLevelEnum))
            assert traces_sampler({"wsgi_environ": wsgi_environ}) == 1.0

        def test_healthcheck_takes_precedence_over_trace_cookie(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.TRACE], path_info="/healthcheck")
            assert traces_sampler({"wsgi_environ": wsgi_environ}) == 0

    class TestProfilesSampler:
        def test_healthcheck_is_never_sampled(self, app):
            assert profiles_sampler({"wsgi_environ": {"PATH_INFO": "/healthcheck"}}) == 0

        def test_default_sample_rate_when_no_environ(self, app):
            assert profiles_sampler({}) == 0.02

        def test_raises_when_secret_key_not_configured(self, app, monkeypatch):
            import app.sentry as sentry_module

            monkeypatch.setattr(sentry_module, "_secret_key", None)
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.PROFILE])
            with pytest.raises(ValueError, match="Flask application secret key not configured for sentry"):
                profiles_sampler({"wsgi_environ": wsgi_environ})

        def test_default_sample_rate_when_cookie_absent(self, app):
            assert profiles_sampler({"wsgi_environ": {"PATH_INFO": "/anything"}}) == 0.02

        def test_default_sample_rate_when_cookie_signed_with_wrong_secret(self, app):
            wsgi_environ = _cookie_environ("not-the-secret", [TraceLevelEnum.PROFILE])
            assert profiles_sampler({"wsgi_environ": wsgi_environ}) == 0.02

        def test_default_sample_rate_when_cookie_only_has_trace_level(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.TRACE])
            assert profiles_sampler({"wsgi_environ": wsgi_environ}) == 0.02

        def test_default_sample_rate_when_cookie_only_has_debug_logging_level(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.DEBUG_LOGGING])
            assert profiles_sampler({"wsgi_environ": wsgi_environ}) == 0.02

        def test_force_sampled_when_cookie_has_profile_level(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.PROFILE])
            assert profiles_sampler({"wsgi_environ": wsgi_environ}) == 1.0

        def test_force_sampled_when_cookie_has_all_levels(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], list(TraceLevelEnum))
            assert profiles_sampler({"wsgi_environ": wsgi_environ}) == 1.0

        def test_healthcheck_takes_precedence_over_trace_cookie(self, app):
            wsgi_environ = _cookie_environ(app.config["SECRET_KEY"], [TraceLevelEnum.PROFILE], path_info="/healthcheck")
            assert profiles_sampler({"wsgi_environ": wsgi_environ}) == 0
