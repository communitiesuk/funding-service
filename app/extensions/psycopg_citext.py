"""
psycopg doesn't ship with `citext` registered as a known type - citext comes from an extension on the database
(unique OID per-database) rather than a built-in type.

psycopg/ postgres defaults to processing unknown type OIDs as text. This works for scalar values but means arrays
of `citext` get turned into a string literal (eg `'{a.gov.uk,b.gov.uk}'`) rather than a list.

We lookup and register the dynamic type OID for citext (returned with every data row that is fetched) on the db
connection, now when that OID is received by the client it will register an array processor to correctly deal
with arrays of citext (the default text fallback continues to be fine for scalar values).

Note this should apply to the app, scripts that run in the app context and migrations (Flask-Migrate runs
Alembic against the app's engine).
"""

from typing import Any

import sqlalchemy.event as sa_event
from flask import Flask
from flask_sqlalchemy_lite import SQLAlchemy
from psycopg import Connection
from psycopg.types import TypeInfo
from sqlalchemy import Engine


class PsycopgCitextExtension:
    def __init__(self, app: Flask | None = None, db: SQLAlchemy | None = None) -> None:
        if app and db:
            self.init_app(app, db)

    def init_app(self, app: Flask, db: SQLAlchemy) -> None:
        with app.app_context():
            self._listen(db.engine)

    def _listen(self, engine: Engine) -> None:
        sa_event.listen(engine, "connect", self._register_citext, named=True)

    @staticmethod
    def _register_citext(dbapi_connection: Connection[Any], **kwargs: Any) -> None:
        citext = TypeInfo.fetch(dbapi_connection, "citext")

        # the extension isn't installed in the database so no OID is assigned
        # default postgres fallback will return values as text
        if citext is not None:
            citext.register(dbapi_connection)
