from datetime import datetime, timedelta

import pytest

from app.common.data.models import MagicLink


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_create_magic_link_frozen_time(db_session, factories, time_freezer):
    factory_ml = factories.magic_link.create()
    magic_link = magic_link = db_session.get(MagicLink, factory_ml.id)
    assert magic_link.created_at_utc == datetime(2025, 1, 1, 13, 30, 0)


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_update_magic_link_frozen_time_no_tick(db_session, factories, time_freezer):
    factory_ml = factories.magic_link.create()
    magic_link = db_session.get(MagicLink, factory_ml.id)
    assert magic_link.created_at_utc == datetime(2025, 1, 1, 13, 30, 0)
    assert magic_link.updated_at_utc == datetime(2025, 1, 1, 13, 30, 0)
    magic_link.claimed_at = datetime.now()
    db_session.add(magic_link)
    db_session.flush()
    magic_link = magic_link = db_session.get(MagicLink, factory_ml.id)
    assert magic_link.updated_at_utc == datetime(2025, 1, 1, 13, 30, 0)


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_update_magic_link_frozen_time_with_tick(db_session, factories, time_freezer):
    factory_ml = factories.magic_link.create()
    magic_link = magic_link = db_session.get(MagicLink, factory_ml.id)
    assert magic_link.created_at_utc == datetime(2025, 1, 1, 13, 30, 0)
    assert magic_link.updated_at_utc == datetime(2025, 1, 1, 13, 30, 0)

    time_freezer.update_frozen_time(timedelta(hours=1))
    magic_link.claimed_at_utc = datetime.now()

    db_session.add(magic_link)
    db_session.flush()
    magic_link = magic_link = db_session.get(MagicLink, factory_ml.id)
    assert magic_link.updated_at_utc == datetime(2025, 1, 1, 14, 30, 0)


@pytest.mark.xfail
def test_request_fixture_without_time_raises_value_error(time_freezer, db_session):
    # Testing validation inside the time_freezer fixture - this should fail as no freeze_time marker provided
    pass


@pytest.mark.xfail
@pytest.mark.freeze_time("dodgy time string")
def test_request_fixture_invalid_time_raises_value_error(time_freezer, db_session):
    # Testing validation inside the time_freezer fixture - this should fail as no freeze_time marker provided
    pass
