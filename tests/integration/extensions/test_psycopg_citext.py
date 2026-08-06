from sqlalchemy.orm import Session


class TestPsycopgCitextExtension:
    def test_citext_arrays_are_loaded_as_lists_of_strings(self, db_session: Session):
        # regression test against the extension not being registered on the engine
        # and psycopg returning a string literal ('{a.gov.uk,b.gov.uk}')
        value = db_session.connection().exec_driver_sql("select array['a.gov.uk', 'b.gov.uk']::citext[]").scalar()

        assert value == ["a.gov.uk", "b.gov.uk"]
