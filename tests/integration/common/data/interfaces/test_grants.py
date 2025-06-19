import pytest

from app.common.data.interfaces.grants import (
    DuplicateValueError,
    create_grant,
    get_all_grants,
    get_all_grants_by_user,
    get_grant,
    grant_name_exists,
    update_grant,
)
from app.common.data.models import Grant
from app.common.data.types import RoleEnum


def test_get_grant(factories):
    g = factories.grant.create()
    result = get_grant(g.id)
    assert result is not None


def test_get_all_grants_platform_admin(factories):
    user_obj = factories.user.create(email="testadmin@communities.gov.uk")
    factories.user_role.create(user=user_obj, role=RoleEnum.ADMIN)
    factories.grant.create_batch(5)
    result = get_all_grants_by_user(user_obj)
    assert len(result) == 5


def test_get_all_grants_member(factories):
    user_member = factories.user.create(email="testmember@communities.gov.uk")
    grants = factories.grant.create_batch(5)
    factories.user_role.create(user=user_member, role=RoleEnum.MEMBER, grant=grants[0])
    result = get_all_grants_by_user(user_member)
    assert len(result) == 1


def test_get_all_grants_by_user(factories):
    factories.grant.create_batch(5)
    result = get_all_grants()
    assert len(result) == 5


def test_create_grant(db_session) -> None:
    result = create_grant(
        ggis_number="GGIS-12345",
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
            ggis_number="GGIS-12345",
            name="Duplicate Grant",
            description="This is a duplicate grant.",
            primary_contact_name="Jane Doe",
            primary_contact_email="janedoe@example.com",
        )
    assert e.value.model_name == "grant"
    assert e.value.field_name == "name"


def test_update_grant_success(factories) -> None:
    grant = factories.grant.create(name="test_grant")
    update_grant(
        grant=grant,
        name="test_grant_updated",
        description="Updated grant description",
        primary_contact_name="Updated primary contact name",
        primary_contact_email="Updated primary contact email",
        ggis_number="GGIS-UPDATED",
    )

    assert grant.name == "test_grant_updated"
    assert grant.description == "Updated grant description"
    assert grant.primary_contact_name == "Updated primary contact name"
    assert grant.primary_contact_email == "Updated primary contact email"
    assert grant.ggis_number == "GGIS-UPDATED"


def test_update_grant_duplicate_name(factories):
    grant_1 = factories.grant.create(name="test_grant")
    factories.grant.create(name="test_grant_2")
    with pytest.raises(DuplicateValueError):
        update_grant(grant=grant_1, name="test_grant_2")


def test_updated_grant_nothing_provided(factories) -> None:
    grant = factories.grant.create(
        name="test_grant",
        description="Initial description",
        primary_contact_name="Initial Contact",
        primary_contact_email="Initial Email",
        ggis_number="GGIS-123456",
    )
    updated_grant = update_grant(grant=grant)

    assert updated_grant.name == "test_grant"
    assert updated_grant.description == "Initial description"
    assert updated_grant.primary_contact_name == "Initial Contact"
    assert updated_grant.primary_contact_email == "Initial Email"
    assert updated_grant.ggis_number == "GGIS-123456"


class TestGrantNameExists:
    def test_grant_name_exists_true(self, factories):
        factories.grant.create(name="Existing Grant")

        result = grant_name_exists("Existing Grant")
        assert result is True

    def test_grant_name_exists_false(self, factories):
        result = grant_name_exists("Non-existent Grant")
        assert result is False

    def test_grant_name_exists_case_insensitive(self, factories):
        factories.grant.create(name="Existing Grant")

        result = grant_name_exists("existing grant")
        assert result is True

    def test_grant_name_exists_exclude_current_grant(self, factories):
        grant = factories.grant.create(name="Test Grant")

        # Should return False when excluding the current grant
        assert grant_name_exists("Test Grant", exclude_grant_id=grant.id) is False

        # Should return True when not excluding
        assert grant_name_exists("Test Grant") is True
