import pytest

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions


class TestFlushAndRollbackOnExceptions:
    def test_flushes_session_on_exception(self, factories, db_session):
        def add_thing_to_session():
            user = factories.user.build()
            assert db_session._is_clean()

            db_session.add(user)
            assert not db_session._is_clean()

        # Without decorator, should leave the session with pending modifications
        add_thing_to_session()
        assert not db_session._is_clean()

        db_session.rollback()
        assert db_session._is_clean()

        # When wrapped, should flush pending modifications to the DB, leaving the session 'clean'
        flush_and_rollback_on_exceptions(add_thing_to_session)()
        assert db_session._is_clean()

    def test_exceptions_automatically_rollback(self, factories, db_session):
        user = factories.user.build()

        def add_thing_to_session(user_):
            assert db_session._is_clean()
            db_session.add(user_)
            assert user_ in db_session
            assert not db_session._is_clean()
            raise ValueError("Something went wrong")

        with pytest.raises(ValueError):
            flush_and_rollback_on_exceptions(add_thing_to_session)(user)

        assert db_session._is_clean()
        assert user not in db_session

    def test_exceptions_can_be_coerced(self, factories, db_session):
        class ExceptionWrapped(Exception):
            def __init__(self, original_exception: Exception):
                self.original_exception = original_exception

        user = factories.user.build()

        @flush_and_rollback_on_exceptions(coerce_exceptions=[(ValueError, ExceptionWrapped)])
        def raise_error(user_):
            db_session.add(user_)
            raise ValueError("Something went wrong")

        with pytest.raises(ExceptionWrapped):
            raise_error(user)
