from functools import wraps
from typing import Any, Callable, cast

import sqlalchemy.orm as orm
from flask import Response, g
from flask.sansio.app import App
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy.exc import PendingRollbackError


class DBRequestSession:
    def __init__(self, db: SQLAlchemy):
        self._db = db

    def init_app(self, app: App) -> None:
        app.extensions["fs_db_request_session"] = self
        app.after_request(_commit_session)  # commits can still fail, this happens before error handlers
        app.teardown_appcontext(_close_session)

    @property
    def request_session(self) -> orm.Session:
        return g.get("_fs_db_request_session", None) or self._db.session

    # see https://mypy.readthedocs.io/en/stable/generics.html#declaring-decorators
    def db_request_auto_commit[F: Callable[..., Any]](self, func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            g._fs_db_request_session = self._db.sessionmaker(autoflush=True)
            return func(*args, **kwargs)

        return cast(F, wrapper)


def _commit_session(response: Response) -> Response:
    session: orm.Session | None = g.get("_fs_db_request_session", None)
    if session:
        # we should only commit if the session hasn't previously been rolled back
        # it looks the session is autorolledback after a integrity check (i.e a flush)
        # in which case we shouldn't commit here
        try:
            session.commit()
        # want to sense check if we can check for this up front but have seen
        # this done in a few places
        except PendingRollbackError:
            session.rollback()
    return response


def _close_session(e: BaseException | None) -> None:
    session: orm.Session | None = g.get("_fs_db_request_session", None)
    if session is None:
        return
    else:
        session.close()
