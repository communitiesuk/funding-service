import pytest

from app.common.data.interfaces.collections import create_collection_schema
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import CollectionSchema


def test_create_collection(db_session, factories):
    g = factories.grant.create()
    u = factories.user.create()
    collection = create_collection_schema(name="test_collection", user=u, grant=g)
    assert collection is not None
    assert collection.id is not None

    from_db = db_session.get(CollectionSchema, collection.id)
    assert from_db is not None


def test_create_collection_name_is_unique_per_grant(db_session, factories):
    grants = factories.grant.create_batch(2)
    u = factories.user.create()

    create_collection_schema(name="test_collection", user=u, grant=grants[0])
    collection_same_name_different_grant = create_collection_schema(name="test_collection", user=u, grant=grants[1])

    assert collection_same_name_different_grant.id is not None

    with pytest.raises(DuplicateValueError):
        create_collection_schema(name="test_collection", user=u, grant=grants[0])
