import pytest
from factory.alchemy import SQLAlchemyModelFactory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.grants import add_grant, get_grant
from app.common.data.models import Grant


def test_get_grant(grant_factory: SQLAlchemyModelFactory):
    g = grant_factory.create()
    result = get_grant(g.id)
    assert result is not None


def test_create_grant(db: SQLAlchemy, grant_factory: SQLAlchemyModelFactory) -> None:
    result = add_grant(name="test_grant")
    assert result is not None
    assert result.id is not None

    from_db = db.get_session().get(Grant, result.id)
    assert from_db is not None


def test_create_duplicate_grant(grant_factory: SQLAlchemyModelFactory) -> None:
    grant_factory.create(name="duplicate_grant")
    with pytest.raises(IntegrityError) as e:
        add_grant(name="duplicate_grant")
    assert 'duplicate key value violates unique constraint "uq_grant_name"' in str(e.value)
