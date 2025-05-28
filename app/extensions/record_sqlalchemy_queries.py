"""
A modification of https://github.com/pallets-eco/flask-sqlalchemy/blob/main/src/flask_sqlalchemy/record_queries.py
adapted for use in our app, as Flask-SQLAlchemy-Lite does not provide this behaviour.

Licence on the original source code for this file only:
---
Copyright 2010 Pallets

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1.  Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.

2.  Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

3.  Neither the name of the copyright holder nor the names of its
    contributors may be used to endorse or promote products derived from
    this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import dataclasses
import inspect
import typing as t
from time import perf_counter

import sqlalchemy as sa
import sqlalchemy.event as sa_event
from flask import Flask, current_app, g, has_app_context
from flask_sqlalchemy_lite import SQLAlchemy


@dataclasses.dataclass
class QueryInfo:
    statement: str | None
    parameters: t.Any
    start_time: float
    end_time: float
    location: str

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class RecordSqlalchemyQueriesExtension:
    def __init__(self, app: Flask | None = None, db: SQLAlchemy | None = None) -> None:
        if app and db:
            self.init_app(app, db)

    def init_app(self, app: Flask, db: SQLAlchemy) -> None:
        if app.config["RECORD_SQLALCHEMY_QUERIES"]:
            app.extensions["record_sqlalchemy_queries"] = self

            with app.app_context():
                self._listen(db.engine)

    def _listen(self, engine: sa.engine.Engine) -> None:
        sa_event.listen(engine, "before_cursor_execute", self._record_start, named=True)
        sa_event.listen(engine, "after_cursor_execute", self._record_end, named=True)

    @staticmethod
    def _record_start(context: sa.engine.ExecutionContext, **kwargs: t.Any) -> None:
        if not has_app_context():
            return

        context._rsq_start_time = perf_counter()  # type: ignore[attr-defined]

    @staticmethod
    def _record_end(context: sa.engine.ExecutionContext, **kwargs: t.Any) -> None:
        if not has_app_context():
            return

        if "_recorded_sqlalchemy_queries" not in g:
            g._recorded_sqlalchemy_queries = []

        import_top = current_app.import_name.partition(".")[0]
        import_dot = f"{import_top}."
        frame = inspect.currentframe()

        while frame:
            name = frame.f_globals.get("__name__")

            if name and (name == import_top or name.startswith(import_dot)):
                code = frame.f_code
                location = f"{code.co_filename}:{frame.f_lineno} ({code.co_name})"
                break

            frame = frame.f_back
        else:
            location = "<unknown>"

        g._recorded_sqlalchemy_queries.append(
            QueryInfo(
                statement=context.statement,
                parameters=context.parameters,
                start_time=context._rsq_start_time,  # type: ignore[attr-defined]
                end_time=perf_counter(),
                location=location,
            )
        )


def get_recorded_queries() -> list[QueryInfo]:
    return t.cast(list[QueryInfo], g.get("_recorded_sqlalchemy_queries", []))
