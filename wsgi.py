from gevent import monkey

monkey.patch_all()

from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from app import create_app  # noqa: E402
from app.sentry import IgnoreIncomingTraceHeaders  # noqa: E402

flask_app = create_app()

# ProxyFix must wrap the Flask app object here, not `app.wsgi_app`, so that it runs before
# sentry-sdk's WSGI middleware (sentry-sdk patches Flask.__call__, making itself the outermost
# layer, and reads the request URL from the raw environ). If ProxyFix ran inside Flask, Sentry
# would record the ALB URL rather than the public CloudFront URL.
# IgnoreIncomingTraceHeaders is the outermost layer for the same reason: sentry-sdk's middleware continues a trace from
# the `sentry-trace`/`baggage` headers in the raw environ, so they must be stripped before it runs.
# NB: Flask CLI auto-discovery (used where FLASK_APP is unset, eg `flask db upgrade` in deployed
# containers) still works because `flask_app` is the only Flask instance in this module.
app = IgnoreIncomingTraceHeaders(
    ProxyFix(
        flask_app,
        x_for=flask_app.config["PROXY_FIX_FOR"],
        x_proto=flask_app.config["PROXY_FIX_PROTO"],
        x_host=flask_app.config["PROXY_FIX_HOST"],
    )
)

if __name__ == "__main__":
    flask_app.run()
