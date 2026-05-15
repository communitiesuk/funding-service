from app.sentry import profiles_sampler, traces_sampler


class TestSentry:
    class TestTracesSampler:
        def test_healthcheck_is_never_sampled(self, app):
            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/healthcheck"}}) == 0

        def test_default_sample_rate_when_no_environ(self, app):
            assert traces_sampler({}) == 0.02

        def test_default_sample_rate_when_trace_header_absent(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/anything"}}) == 0.02

        def test_default_sample_rate_when_trace_header_wrong(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/anything", "HTTP_X_FORCE_TRACE": "wrong"}}) == 0.02

        def test_force_sampled_when_trace_component_visibility_header_set(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/anything", "HTTP_X_FORCE_TRACE": "secret"}}) == 1.0

        def test_healthcheck_takes_precedence_over_trace_header(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert traces_sampler({"wsgi_environ": {"PATH_INFO": "/healthcheck", "HTTP_X_FORCE_TRACE": "secret"}}) == 0

    class TestProfilesSampler:
        def test_healthcheck_is_never_sampled(self, app):
            assert profiles_sampler({"wsgi_environ": {"PATH_INFO": "/healthcheck"}}) == 0

        def test_default_sample_rate_when_no_environ(self, app):
            assert profiles_sampler({}) == 0.02

        def test_default_sample_rate_when_trace_header_absent(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert profiles_sampler({"wsgi_environ": {"PATH_INFO": "/anything"}}) == 0.02

        def test_default_sample_rate_when_trace_header_wrong(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert profiles_sampler({"wsgi_environ": {"PATH_INFO": "/anything", "HTTP_X_FORCE_TRACE": "wrong"}}) == 0.02

        def test_force_sampled_when_trace_component_visibility_header_set(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert profiles_sampler({"wsgi_environ": {"PATH_INFO": "/anything", "HTTP_X_FORCE_TRACE": "secret"}}) == 1.0

        def test_healthcheck_takes_precedence_over_trace_header(self, app, monkeypatch):
            monkeypatch.setitem(app.config, "FORCE_TRACE_TOKEN", "secret")

            assert (
                profiles_sampler({"wsgi_environ": {"PATH_INFO": "/healthcheck", "HTTP_X_FORCE_TRACE": "secret"}}) == 0
            )
