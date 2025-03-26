import sqlalchemy.orm as orm
from flask import g
from flask.sansio.app import App
from flask_sqlalchemy_lite import SQLAlchemy

# future things - make sure you've tried out and gotten a sense for

# a wrapped method that sets up the managed session on this flask request

# the extension that appropriately hooks into the flask app lifecycle


# it could do things like checking the db its been given is appropriately
# configured and hooked into the app its being registered with but that can happen later if needs to
class DBRequestSession:
    def __init__(self, db: SQLAlchemy):
        self._db = db

    def init_app(self, app: App) -> None:
        app.extensions["fs_db_request_session"] = self
        app.teardown_appcontext(_commit_session)

    # a getter method that can either get the default db session or
    @property
    def request_session(self) -> orm.Session:
        # todo sfount check we don't get into strange circular dependencies with extensions pulling in extensions
        return g.pop("_fs_db_request_session", None) or self._db.session

    def db_request_auto_commit(self) -> None:
        g["_fs_db_request_session"] = self._db.sessionmaker()


def _commit_session(e: BaseException | None) -> None:
    # todo sfount this should probably only act if there isn't an exception?
    session: orm.Session | None = g.pop("_fs_db_request_session", None)
    if session is None:
        return
    else:
        session.commit()
