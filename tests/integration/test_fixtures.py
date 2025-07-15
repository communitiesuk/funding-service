from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.common.data.models import Collection
from app.common.helpers.collections import SubmissionHelper


@pytest.fixture(scope="function", autouse=True)
def setup_temp_tables(db_session):
    db_session.execute(
        text("""CREATE TABLE test_fixtures(
                             id                     uuid PRIMARY KEY,
                             created_at_utc         timestamp without time zone default now(),
                             updated_at_utc         timestamp without time zone default now(),
                             item_name              varchar(10))
                            """)
    )

    yield

    db_session.execute(text("DROP TABLE test_fixtures"))


@pytest.mark.freeze_time("2025-03-01 13:30:00")
def test_create_frozen_time(db_session):
    row_id = uuid4()
    db_session.execute(
        text("INSERT INTO test_fixtures(id, item_name) VALUES (:row_id, 'test 1');"), params={"row_id": row_id}
    )
    created_at_utc = db_session.execute(
        text("SELECT created_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).scalar()
    assert created_at_utc == datetime(2025, 3, 1, 13, 30, 0)


@pytest.mark.freeze_time("2025-02-01 13:30:00")
def test_update_frozen_time_no_tick(db_session):
    row_id = uuid4()
    db_session.execute(
        text("INSERT INTO test_fixtures(id, item_name) VALUES (:row_id, 'test 1');"), params={"row_id": row_id}
    )
    rows = db_session.execute(
        text("SELECT created_at_utc, updated_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).all()
    assert rows[0].created_at_utc == datetime(2025, 2, 1, 13, 30, 0)
    assert rows[0].updated_at_utc == datetime(2025, 2, 1, 13, 30, 0)

    # Try update using db time
    db_session.execute(
        text("UPDATE test_fixtures SET updated_at_utc = NOW() WHERE id=:row_id"), params={"row_id": row_id}
    )
    db_session.flush()
    rows = db_session.execute(
        text("SELECT created_at_utc, updated_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).all()
    assert rows[0].updated_at_utc == datetime(2025, 2, 1, 13, 30, 0)

    # Try update using python time
    db_session.execute(
        text("UPDATE test_fixtures SET updated_at_utc = :python_now WHERE id=:row_id"),
        params={"python_now": datetime.now(), "row_id": row_id},
    )
    db_session.flush()
    rows = db_session.execute(
        text("SELECT created_at_utc, updated_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).all()
    assert rows[0].updated_at_utc == datetime(2025, 2, 1, 13, 30, 0)


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_update_frozen_time_with_tick(db_session, time_freezer):
    row_id = uuid4()
    db_session.execute(
        text("INSERT INTO test_fixtures(id, item_name) VALUES (:row_id, 'test 1');"), params={"row_id": row_id}
    )
    rows = db_session.execute(
        text("SELECT created_at_utc, updated_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).all()
    assert rows[0].created_at_utc == datetime(2025, 1, 1, 13, 30, 0)
    assert rows[0].updated_at_utc == datetime(2025, 1, 1, 13, 30, 0)

    time_freezer.update_frozen_time(timedelta(hours=1))

    # Try update using db time
    db_session.execute(
        text("UPDATE test_fixtures SET updated_at_utc = NOW() WHERE id=:row_id"), params={"row_id": row_id}
    )
    db_session.flush()
    rows = db_session.execute(
        text("SELECT created_at_utc, updated_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).all()
    assert rows[0].updated_at_utc == datetime(2025, 1, 1, 14, 30, 0)

    time_freezer.update_frozen_time(timedelta(hours=1))

    # Try update using python time
    db_session.execute(
        text("UPDATE test_fixtures SET updated_at_utc = :python_now WHERE id=:row_id"),
        params={"python_now": datetime.now(), "row_id": row_id},
    )
    db_session.flush()
    rows = db_session.execute(
        text("SELECT created_at_utc, updated_at_utc FROM test_fixtures WHERE id=:row_id"), params={"row_id": row_id}
    ).all()
    assert rows[0].updated_at_utc == datetime(2025, 1, 1, 15, 30, 0)


@pytest.mark.xfail
@pytest.mark.freeze_time("dodgy time string")
def test_request_fixture_invalid_time_raises_value_error(time_freezer, db_session):
    # Testing validation inside the time_freezer fixture - this should fail as no freeze_time marker provided
    pass


def test_collection_factory_completed_submissions(db_session, factories):
    collection = factories.collection.create(create_completed_submissions__test=3, create_completed_submissions__live=2)

    collection_from_db = db_session.get(Collection, (collection.id, 1))
    assert len(collection_from_db._submissions) == 5
    assert len(collection_from_db.test_submissions) == 3
    assert len(collection_from_db.live_submissions) == 2

    answers_dict = collection._submissions[0].data
    assert len(answers_dict) == 6

    for submission in collection_from_db.test_submissions:
        helper = SubmissionHelper(submission)
        all_questions = collection.sections[0].forms[0].questions
        for question in all_questions:
            assert helper.get_question(question.id).text == question.text
            assert (
                helper.get_answer_for_question(question.id).get_value_for_submission()
                == submission.data[str(question.id)]
            )
