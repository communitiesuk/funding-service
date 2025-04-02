import pytest
from flask import Flask, Response
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy_utils import create_database, database_exists

from app.extensions.db_request_session import AutoCommitAfterRequestExtension


class Base(DeclarativeBase):
    __abstract__ = True


class TableUnderTest(Base):
    __tablename__ = "table_under_test"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(unique=True)


@pytest.fixture(scope="session")
def extensions_app(setup_db_container):
    app = Flask(__name__)

    app.testing = True

    postgres_uri = setup_db_container.replace("+psycopg2", "+psycopg")
    app.config["SQLALCHEMY_ENGINES"] = {"default": postgres_uri + "_test_extensions"}

    db = SQLAlchemy(app)

    auto_commit_after_request_extension = AutoCommitAfterRequestExtension(db=db)
    auto_commit_after_request_extension.init_app(app)

    @app.post("/<value>")
    @auto_commit_after_request_extension
    def handler(value):
        db.session.add(TableUnderTest(value=value))
        return Response(status=200)

    @app.post("/handles/<value>")
    @auto_commit_after_request_extension
    def hanlder_integrity_handler_not_rolled_back(value):
        try:
            db.session.add(TableUnderTest(value=value))
            db.session.flush()
        except IntegrityError:
            pass

        return Response(status=200)

    return app


@pytest.fixture(scope="session")
def extensions_db(extensions_app):
    with extensions_app.app_context():
        no_db = not database_exists(extensions_app.config["SQLALCHEMY_ENGINES"]["default"])

        if no_db:
            create_database(extensions_app.config["SQLALCHEMY_ENGINES"]["default"])

        TableUnderTest.metadata.create_all(extensions_app.extensions["sqlalchemy"].engines["default"])
    yield extensions_app.extensions["sqlalchemy"]

    with extensions_app.app_context():
        for engine in extensions_app.extensions["sqlalchemy"].engines.values():
            engine.dispose()


@pytest.fixture(scope="function")
def sensible_sessions(extensions_app, extensions_db):
    with extensions_app.app_context():
        connection = extensions_db.engine.connect()
        transaction = connection.begin()

        original_configuration = extensions_db.sessionmaker.kw.copy()
        extensions_db.sessionmaker.configure(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield extensions_db.session

        finally:
            # Restore the original sessionmaker configuration.
            extensions_db.sessionmaker.configure(**original_configuration)

            extensions_db.session.close()
            transaction.rollback()
            connection.close()


def test_db_session_is_committed(extensions_app, extensions_db, sensible_sessions):
    response = extensions_app.test_client().post("/a-value")

    # set up a separate transaction iwth the database to ensure it was actually commited following
    entity = extensions_db.sessionmaker().get(TableUnderTest, 1)
    assert response.status_code == 200
    assert entity is not None


def test_db_session_is_rolled_back_and_doesnt_error_when_handled(extensions_app, extensions_db, sensible_sessions):
    first_response = extensions_app.test_client().post("/a-value")
    duplicate_response = extensions_app.test_client().post("/handles/a-value")

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 200

    all_entities = extensions_db.sessionmaker().scalars(select(TableUnderTest)).all()
    assert len(all_entities) == 1


def test_db_session_throws_appropriately_on_commit_if_not_handled(extensions_app, extensions_db, sensible_sessions):
    extensions_app.test_client().post("/a-value")

    with pytest.raises(IntegrityError):
        extensions_app.test_client().post("/a-value")

    all_entities = extensions_db.sessionmaker().scalars(select(TableUnderTest)).all()
    assert len(all_entities) == 1
