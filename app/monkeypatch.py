from flask_sqlalchemy_lite import _extension


def patch_sqlalchemy_lite_async() -> None:
    # Monkey patch to prevent app.teardown_appcontext(_close_async_sessions)
    # When run with Gunicorn and Gevent this causes the error 'You cannot use AsyncToSync in the same thread
    # as an async event loop - just await the async function directly.'
    # This should be safe to do as we're not using async sessions currently
    # See context: https://github.com/pallets-eco/flask-sqlalchemy-lite/issues/11
    # and https://github.com/benoitc/gunicorn/issues/3070
    def noop(*args: object, **kwargs: object) -> None:
        pass

    _extension._close_async_sessions = noop  # type: ignore[assignment] # Override the function with a no-op
