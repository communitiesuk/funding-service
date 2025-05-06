from datetime import datetime, timedelta

from freezegun import freeze_time
from sqlalchemy import text
from sqlalchemy.orm import Session


class TimeFreezer:
    time_format: str = "%Y-%m-%d %H:%M:%S"

    def __init__(self, frozen_time: str, session: Session) -> None:
        self.frozen_time = datetime.strptime(frozen_time, self.time_format)
        self.session = session
        self._setup_db_freezer()
        self._setup_python_freezer()

    def _setup_db_freezer(self) -> None:
        # Update the now() function in the database to return our frozen time
        select_existing_now_function_sql = "select prosrc from pg_proc where proname='now'"
        override_now_function_sql = (
            "CREATE OR REPLACE FUNCTION pg_catalog.now() RETURNS timestamptz AS "
            "$$SELECT current_setting('test.freeze_time')::timestamptz$$ language sql;"
        )
        self.existing_now_function_source = self.session.execute(text(select_existing_now_function_sql)).scalar()
        self.session.execute(text(f"SET LOCAL test.freeze_time = '{self.frozen_time.strftime(self.time_format)}'"))
        self.session.execute(text(override_now_function_sql))

    def _restore_db_time(self) -> None:
        restore_now_function_sql = (
            ""
            + "create or replace function pg_catalog.now() "
            + "RETURNS TIMESTAMP WITH TIME ZONE AS "
            + f"$${self.existing_now_function_source}$$ LANGUAGE internal;"
        )
        self.session.execute(text(restore_now_function_sql))

    def _setup_python_freezer(self) -> None:
        # Use freezegun to override calls to now() in code (not db)
        self.freezer = freeze_time(self.frozen_time, ignore=["_pytest.runner", "_pytest.terminal"])
        self.freezer_movable = self.freezer.start()

    def _restore_python_time(self) -> None:
        self.freezer.stop()

    def update_frozen_time(self, time_delta: timedelta) -> None:
        self.frozen_time += time_delta
        self.session.execute(
            text(f"SET LOCAL test.freeze_time = '{self.frozen_time.strftime(self.time_format)}'"),
        )
        self.freezer_movable.move_to(self.frozen_time)

    def restore_actual_time(self) -> None:
        self._restore_python_time()
        self._restore_db_time()
