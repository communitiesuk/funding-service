from functools import wraps

import sqlalchemy.orm as orm
from flask import g
from flask.sansio.app import App
from flask_sqlalchemy_lite import SQLAlchemy


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

    def db_request_auto_commit(self, func):  # type: ignore[no-untyped-def]
        @wraps(func)
        def decorator(*args, **kwargs):  # type: ignore[no-untyped-def]
            g._fs_db_request_session = self._db.sessionmaker(autoflush=True)
            return func(*args, **kwargs)

        return decorator


def _commit_session(response) -> None:  # type: ignore[no-untyped-def]
    session: orm.Session | None = g.get("_fs_db_request_session", None)
    if session:
        session.commit()
    return response


def _close_session(e: BaseException | None) -> None:
    session: orm.Session | None = g.get("_fs_db_request_session", None)
    if session is None:
        return
    else:
        session.close()
