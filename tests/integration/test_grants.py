import pytest
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.grants import add_grant, get_all_grants, get_grant
from app.common.data.models import Grant


def test_get_grant(grant_factory):
    g = grant_factory.create()
    result = get_grant(g.id)
    assert result is not None


def test_get_all_grants(grant_factory):
    grant_factory.create_batch(5)
    result = get_all_grants()
    assert len(result) == 5


def test_create_grant(db, grant_factory) -> None:
    result = add_grant(name="test_grant")
    assert result is not None
    assert result.id is not None

    from_db = db.get_session().get(Grant, result.id)
    assert from_db is not None


def test_create_duplicate_grant(grant_factory) -> None:
    grant_factory.create(name="duplicate_grant")
    with pytest.raises(IntegrityError) as e:
        add_grant(name="Duplicate_Grant")
    assert 'duplicate key value violates unique constraint "uq_grant_name"' in str(e.value)
