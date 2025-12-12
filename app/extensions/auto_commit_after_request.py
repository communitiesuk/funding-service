from functools import wraps
from typing import Callable

from flask import Response, g
from flask.sansio.app import App
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy.exc import PendingRollbackError


class AutoCommitAfterRequestExtension:
    """
    Provides a callable method to call `commit` on the Flask SQLAlchemy session
    at the end of a request lifecyle.

    Use an instance of this as a decorator on Flask HTTP handlers.

    ```
    auto_commit_after_request = AutoCommitAfterRequestExtension(db=db)

    @app.get("/")
    @auto_commit_after_request
    def handler():
        pass
    ```
    """

    def __init__(self, db: SQLAlchemy):
        self._db = db

    def init_app(self, app: App) -> None:
        app.extensions["fs_auto_commit_after_request"] = self
        app.after_request(self._commit_session)

    # see https://mypy.readthedocs.io/en/stable/generics.html#declaring-decorators
    def __call__[**P, T](self, func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            g._fs_should_auto_commit = True
            return func(*args, **kwargs)

        return wrapper

    def _commit_session(self, response: Response) -> Response:
        # as this is hooked into "after_request" this was never called on failing responses
        # which is the default Flask behaviour. As we now have @app.errorhandler for 400/500 errors
        # and return a new response object this _will_ trigger the "after_request" and we should
        # only be committing if the original response was successful
        if g.get("_fs_should_auto_commit", False):
            success_response = 200 <= response.status_code < 400
            if success_response:
                try:
                    self._db.session.commit()
                except PendingRollbackError:
                    # an integrity error or similar has already been caught by the session (through a `flush`)
                    # this may have been handled by the http handler already, make sure we clean up the session
                    # but then continue
                    # any other failures here should be raised and handled by the flask exception handler stack
                    self._db.session.rollback()
            else:
                # uncomitted changes should be removed at the end of the session but we'll
                # actively rollback just to be sure
                self._db.session.rollback()

        return response
