from gevent import monkey

monkey.patch_all()

from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from app import create_app  # noqa: E402

flask_app = create_app()

# ProxyFix must wrap the Flask app object here, not `app.wsgi_app`, so that it runs before
# sentry-sdk's WSGI middleware (sentry-sdk patches Flask.__call__, making itself the outermost
# layer, and reads the request URL from the raw environ). If ProxyFix ran inside Flask, Sentry
# would record the ALB URL rather than the public CloudFront URL.
# NB: Flask CLI auto-discovery (used where FLASK_APP is unset, eg `flask db upgrade` in deployed
# containers) still works because `flask_app` is the only Flask instance in this module.
app = ProxyFix(flask_app, x_proto=flask_app.config["PROXY_FIX_PROTO"], x_host=flask_app.config["PROXY_FIX_HOST"])

if __name__ == "__main__":
    flask_app.run()
