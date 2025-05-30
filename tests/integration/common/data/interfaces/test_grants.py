import pytest

from app.common.data.interfaces.grants import DuplicateValueError, create_grant, get_all_grants, get_grant, update_grant
from app.common.data.models import Grant


def test_get_grant(factories):
    g = factories.grant.create()
    result = get_grant(g.id)
    assert result is not None


def test_get_all_grants(factories):
    factories.grant.create_batch(5)
    result = get_all_grants()
    assert len(result) == 5


def test_create_grant(db_session) -> None:
    result = create_grant(
        name="Test Grant",
        description="This is a test grant.",
        primary_contact_name="John Doe",
        primary_contact_email="johndoe@example.com",
    )
    assert result is not None
    assert result.id is not None

    from_db = db_session.get(Grant, result.id)
    assert from_db is not None


def test_create_duplicate_grant(factories) -> None:
    factories.grant.create(name="Duplicate Grant")
    with pytest.raises(DuplicateValueError) as e:
        create_grant(
            name="Duplicate Grant",
            description="This is a duplicate grant.",
            primary_contact_name="Jane Doe",
            primary_contact_email="janedoe@example.com",
        )
    assert e.value.model_name == "grant"
    assert e.value.field_name == "name"


def test_update_grant_name(factories) -> None:
    grant_1 = factories.grant.create(name="test_grant")
    factories.grant.create(name="test_grant_2")

    g = get_grant(grant_1.id)
    update_grant(g, name="test_grant_updated")

    g = get_grant(grant_1.id)
    assert g.name == "test_grant_updated"

    with pytest.raises(DuplicateValueError) as e:
        update_grant(g, name="test_grant_2")
        assert e.value.model_name == "grant"
        assert e.value.field_name == "name"
        assert e.value.new_value == "test_grant_2"
