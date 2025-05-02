from datetime import datetime, timedelta
from time import sleep

import pytest
from sqlalchemy import select

from app.common.data.models import MagicLink


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_create_magic_link_frozen_time(db_session, factories, time_freezer):
    factory_ml = factories.magic_link.create()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.created_at == datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")


def test_create_and_update_magic_link_without_frozen_time(db_session, factories):
    factory_ml = factories.magic_link.create()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.created_at != datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")
    assert magic_link.updated_at == magic_link.created_at
    sleep(1)
    magic_link.claimed_at = datetime.now()
    db_session.add(magic_link)
    db_session.flush()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.updated_at != magic_link.created_at


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_update_magic_link_frozen_time_no_tick(db_session, factories, time_freezer):
    factory_ml = factories.magic_link.create()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.created_at == datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")
    assert magic_link.updated_at == datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")
    sleep(1)
    magic_link.claimed_at = datetime.now()
    db_session.add(magic_link)
    db_session.flush()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.updated_at == datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")


@pytest.mark.freeze_time("2025-01-01 13:30:00")
def test_update_magic_link_frozen_time_with_tick(db_session, factories, time_freezer):
    factory_ml = factories.magic_link.create()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.created_at == datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")
    assert magic_link.updated_at == datetime.strptime("2025-01-01 13:30:00", "%Y-%m-%d %H:%M:%S")
    time_freezer.update_frozen_time(timedelta(hours=1))
    magic_link.claimed_at = datetime.now()
    db_session.add(magic_link)
    db_session.flush()
    magic_link = db_session.scalar(select(MagicLink).where(MagicLink.id == factory_ml.id))
    assert magic_link.updated_at == datetime.strptime("2025-01-01 14:30:00", "%Y-%m-%d %H:%M:%S")


@pytest.mark.xfail
def test_request_fixture_without_time_raises_value_error(time_freezer, db_session):
    # Testing validation inside the time_freezer fixture - this should fail as no freeze_time marker provided
    pass


@pytest.mark.xfail
@pytest.mark.freeze_time("dodgy time string")
def test_request_fixture_invalid_time_raises_value_error(time_freezer, db_session):
    # Testing validation inside the time_freezer fixture - this should fail as no freeze_time marker provided
    pass
