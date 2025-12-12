import pytest
from flask import Flask, Response
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy_utils import create_database, database_exists

from app.extensions.auto_commit_after_request import AutoCommitAfterRequestExtension


class Base(DeclarativeBase):
    __abstract__ = True


class TableUnderTest(Base):
    __tablename__ = "table_under_test"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(unique=True)


@pytest.fixture(scope="session")
def app(setup_db_container):
    app = Flask(__name__)

    app.testing = True

    postgres_uri = setup_db_container.get_connection_url().replace("+psycopg2", "+psycopg")
    app.config["SQLALCHEMY_ENGINES"] = {"default": postgres_uri + "_test_extensions"}

    db = SQLAlchemy(app)

    auto_commit_after_request_extension = AutoCommitAfterRequestExtension(db=db)
    auto_commit_after_request_extension.init_app(app)

    @app.errorhandler(500)
    def emulate_handles_error(response):
        # returns a response as if we're returning a nicely formatted template
        return "OK", 500

    @app.post("/<value>")
    @auto_commit_after_request_extension
    def handler(value):
        db.session.add(TableUnderTest(value=value))
        return Response(status=200)

    @app.post("/handles/<value>")
    @auto_commit_after_request_extension
    def handler_integrity_handler_not_rolled_back(value):
        try:
            db.session.add(TableUnderTest(value=value))
            db.session.flush()
        except IntegrityError:
            pass

        return Response(status=200)

    @app.post("/raises/<value>")
    @auto_commit_after_request_extension
    def handler_raises(value):
        db.session.add(TableUnderTest(value=value))
        db.session.flush()
        raise Exception("App failure")

    return app


@pytest.fixture(scope="function")
def db_session(app, db):
    # note that intentionally don't use the `db_session` test isolation in these extension
    # tests to have full confidence that anything that has been mutated by the app is appropriately
    # committed to the database by the extension
    pass


@pytest.fixture(scope="session")
def db(app):
    with app.app_context():
        no_db = not database_exists(app.config["SQLALCHEMY_ENGINES"]["default"])

        if no_db:
            create_database(app.config["SQLALCHEMY_ENGINES"]["default"])

        TableUnderTest.metadata.create_all(app.extensions["sqlalchemy"].engines["default"])
    yield app.extensions["sqlalchemy"]

    with app.app_context():
        for engine in app.extensions["sqlalchemy"].engines.values():
            engine.dispose()


@pytest.fixture(scope="function")
def session_outside_connection(db):
    # set up a separate connection to the database to make sure we don't get a re-used session
    # and are only checking committed values
    connection = db.engine.connect()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    connection.close()


def test_db_session_is_committed(app, db, db_session, session_outside_connection):
    response = app.test_client().post("/first-scenario-value")

    entity = session_outside_connection.get(TableUnderTest, 1)
    assert response.status_code == 200
    assert entity is not None


def test_db_session_is_rolled_back_and_doesnt_error_when_handled(app, db, db_session, session_outside_connection):
    first_response = app.test_client().post("/second-scenario-value")
    duplicate_response = app.test_client().post("/handles/second-scenario-value")

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 200

    all_entities = session_outside_connection.scalars(
        select(TableUnderTest).filter(TableUnderTest.value == "second-scenario-value")
    ).all()
    assert len(all_entities) == 1


def test_db_session_throws_appropriately_on_commit_if_not_handled(app, db, db_session, session_outside_connection):
    app.test_client().post("/third-scenario-value")

    with pytest.raises(IntegrityError):
        app.test_client().post("/third-scenario-value")

    all_entities = session_outside_connection.scalars(
        select(TableUnderTest).filter(TableUnderTest.value == "third-scenario-value")
    ).all()
    assert len(all_entities) == 1


def test_db_session_not_commited_on_failed_response(app, session_outside_connection, mocker):
    mocker.patch.dict(app.config, {"TESTING": False})

    response = app.test_client().post("/raises/fourth-scenario-value")
    assert response.status_code == 500

    entity = session_outside_connection.scalars(
        select(TableUnderTest).filter(TableUnderTest.value == "fourth-scenario-value")
    ).first()
    assert entity is None
