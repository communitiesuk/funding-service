import pytest
from _pytest._code import ExceptionInfo

from app.common.data.interfaces.exceptions import NotEnoughGrantTeamUsersError, StateTransitionError
from app.common.data.interfaces.grants import (
    DuplicateValueError,
    create_grant,
    get_all_deliver_grants_by_user,
    get_all_grants,
    get_grant,
    grant_name_exists,
    update_grant,
)
from app.common.data.models import Grant
from app.common.data.types import GrantStatusEnum, RoleEnum


def test_get_grant(factories):
    g = factories.grant.create()
    result = get_grant(g.id)
    assert result is not None


class TestGetAllDeliverGrantsByUser:
    def test_get_all_grants_platform_admin(self, factories, authenticated_platform_admin_client):
        factories.grant.create_batch(5)
        result = get_all_deliver_grants_by_user(authenticated_platform_admin_client.user)
        assert len(result) == 5

    def test_deliver_org_admin(self, factories, authenticated_org_admin_client):
        factories.grant.create_batch(2, organisation=authenticated_org_admin_client.organisation)
        result = get_all_deliver_grants_by_user(authenticated_org_admin_client.user)
        assert len(result) == 2

    @pytest.mark.xfail
    def test_deliver_org_admin_cannot_see_grants_from_another_org(self, factories, authenticated_org_admin_client):
        raise NotImplementedError("we don't support multiple orgs with can_manage_grants=True yet")

    def test_deliver_org_member(self, factories, authenticated_org_member_client, db_session):
        factories.grant.create_batch(2, organisation=authenticated_org_member_client.organisation)
        result = get_all_deliver_grants_by_user(authenticated_org_member_client.user)
        assert len(result) == 2

    @pytest.mark.xfail
    def test_deliver_org_member_cannot_see_grants_from_another_org(self, factories, authenticated_org_member_client):
        raise NotImplementedError("we don't support multiple orgs with can_manage_grants=True yet")

    def test_get_all_grants_grant_admin(self, factories, authenticated_grant_admin_client):
        factories.grant.create_batch(5)
        result = get_all_deliver_grants_by_user(authenticated_grant_admin_client.user)
        assert result == [authenticated_grant_admin_client.grant]

    def test_get_all_grants_grant_member(self, factories, authenticated_grant_member_client):
        factories.grant.create_batch(5)
        result = get_all_deliver_grants_by_user(authenticated_grant_member_client.user)
        assert result == [authenticated_grant_member_client.grant]


class TestGetAllGrants:
    def test_get_all_grants(self, factories):
        factories.grant.create_batch(5)
        result = get_all_grants()
        assert len(result) == 5

    def test_get_all_grants_by_status(self, factories):
        draft_grants = factories.grant.create_batch(2)
        live_grants = factories.grant.create_batch(2, status=GrantStatusEnum.LIVE)

        result = get_all_grants(statuses=[GrantStatusEnum.DRAFT])
        assert result == draft_grants

        result = get_all_grants(statuses=[GrantStatusEnum.LIVE])
        assert result == live_grants


def test_create_grant(app, db_session) -> None:
    result = create_grant(
        ggis_number="GGIS-12345",
        name="Test Grant",
        code="TG",
        description="This is a test grant.",
        primary_contact_name="John Doe",
        primary_contact_email="johndoe@example.com",
    )
    assert result is not None
    assert result.id is not None

    from_db = db_session.get(Grant, result.id)
    assert from_db is not None
    assert from_db.organisation.name == app.config["PLATFORM_DEPARTMENT_ORGANISATION_CONFIG"]["name"]
    assert from_db.code == "TG"


def test_create_duplicate_grant(factories) -> None:
    factories.grant.create(name="Duplicate Grant")
    with pytest.raises(DuplicateValueError) as e:
        create_grant(
            ggis_number="GGIS-12345",
            name="Duplicate Grant",
            code="DG",
            description="This is a duplicate grant.",
            primary_contact_name="Jane Doe",
            primary_contact_email="janedoe@example.com",
        )
    assert isinstance(e, ExceptionInfo)
    assert e.value.model_name == "grant"
    assert e.value.field_name == "name"


class TestUpdateGrant:
    def test_update_grant_success(self, factories) -> None:
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

    def test_update_grant_duplicate_name(self, factories):
        grant_1 = factories.grant.create(name="test_grant")
        factories.grant.create(name="test_grant_2")
        with pytest.raises(DuplicateValueError):
            update_grant(grant=grant_1, name="test_grant_2")

    def test_updated_grant_nothing_provided(self, factories) -> None:
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

    def test_update_group_status_not_enough_grant_team_users(self, factories):
        grant = factories.grant.create(name="test_grant")
        factories.user_role.create(grant=grant, permissions=[RoleEnum.MEMBER])

        with pytest.raises(NotEnoughGrantTeamUsersError):
            update_grant(grant=grant, status=GrantStatusEnum.LIVE)

        factories.user_role.create(grant=grant, permissions=[RoleEnum.MEMBER])
        updated_grant = update_grant(grant=grant, status=GrantStatusEnum.LIVE)

        assert updated_grant.status == GrantStatusEnum.LIVE

    def test_update_grant_invalid_state_transition(self, factories):
        grant = factories.grant.create(name="test_grant")

        with pytest.raises(StateTransitionError) as e:
            update_grant(grant=grant, status="invalid-state")  # type: ignore[arg-type]

        assert str(e.value) == "Unknown state transition for grant from draft to invalid-state"


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
