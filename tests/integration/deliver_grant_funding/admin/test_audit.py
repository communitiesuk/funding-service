from uuid import uuid4

import pytest
from bs4 import BeautifulSoup

from app.common.audit import (
    DatabaseModelChange,
    UserPermissionsAdded,
    create_database_model_change_for_create,
    create_database_model_change_for_update,
    create_system_event_for_delete,
)
from app.common.data.models_audit import AuditEvent
from app.common.data.types import AuditEventType, RoleEnum
from tests.utils import get_h1_text, get_summary_list_value_by_key


class TestPlatformAdminAuditEventViewAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_audit_event_list_access(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/auditevent/")
        assert response.status_code == expected_code


class TestPlatformAdminAuditEventView:
    def test_displays_audit_events_list(self, authenticated_platform_admin_client, factories, db_session):
        audit_event = factories.audit_event.create(
            data={
                "model_class": "Grant",
                "action": "create",
                "model_id": "123e4567-e89b-12d3-a456-426614174000",
                "changes": {"name": "Test Grant"},
            },
        )

        response = authenticated_platform_admin_client.get("/deliver/admin/auditevent/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Audit Event"

        table = soup.find("table")
        assert table is not None

        table_text = table.get_text()
        assert audit_event.user.email in table_text
        assert "Grant" in table_text
        assert "create" in table_text

    def test_displays_audit_event_detail(self, authenticated_platform_admin_client, factories, db_session):
        actor = factories.user.create()
        grant = factories.grant.create(name="New Name")
        event = DatabaseModelChange(
            user_id=actor.id,
            model_class="Grant",
            model_id=grant.id,
            action="update",
            changes={"name": {"old": "Old Name", "new": "New Name"}},
        )
        audit_event = factories.audit_event.create(user=actor, data=event.model_dump(mode="json"))

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        model_link = soup.find("a", href=f"/deliver/admin/grant/details/?id={grant.id}")
        assert model_link is not None
        assert model_link.get_text(strip=True) == "New Name"
        assert get_summary_list_value_by_key(soup, "Model class").get_text(strip=True) == "Grant"
        assert get_summary_list_value_by_key(soup, "Action").get_text(strip=True) == "update"
        page_text = soup.get_text()
        assert "Old Name" in page_text
        assert "New Name" in page_text
        assert soup.find("pre") is None

    def test_detail_page_renders_the_parsed_event_as_the_top_level_summary_list(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        audit_event = factories.audit_event.create()

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        top_level_list = soup.find("dl", class_="govuk-summary-list")
        top_level_keys = [
            row.find("dt").get_text(strip=True)
            for row in top_level_list.find_all("div", class_="govuk-summary-list__row", recursive=False)
        ]
        assert top_level_keys == ["Event type", "Timestamp", "User", "Action", "Model class", "Model", "Changes"]
        assert "Updated at UTC" not in soup.get_text()

    def test_release_note_event_links_to_custom_endpoint(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        actor = factories.user.create()
        release_note = factories.release_note.create(title="v1")
        event = create_database_model_change_for_create(release_note, actor)
        audit_event = factories.audit_event.create(user=actor, data=event.model_dump(mode="json"))

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        link = soup.find("a", href=f"/deliver/admin/release-note/details/?id={release_note.id}")
        assert link is not None
        assert link.get_text(strip=True) == "v1"

    def test_unknown_model_class_renders_bare_model_id(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        actor = factories.user.create()
        model_id = uuid4()
        event = DatabaseModelChange(
            user_id=actor.id, model_class="Widget", model_id=model_id, action="delete", changes={}
        )
        audit_event = factories.audit_event.create(user=actor, data=event.model_dump(mode="json"))

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        model_value = soup.find("dt", string="Model").find_next_sibling("dd")
        assert model_value.get_text(strip=True) == str(model_id)
        assert model_value.find("a") is None

    def test_displays_user_management_event_with_entity_links(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        actor = factories.user.create(email="actor@example.com")
        target_user = factories.user.create(email="target@example.com")
        organisation = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant = factories.grant.create(name="Test Grant")
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        invitation = factories.invitation.create(email="invited@example.com")
        event = UserPermissionsAdded(
            user_id=actor.id,
            target_user_id=target_user.id,
            organisation_id=organisation.id,
            grant_id=grant.id,
            grant_recipient_id=grant_recipient.id,
            invitation_id=invitation.id,
            permissions=[RoleEnum.DATA_PROVIDER],
            resulting_permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )
        audit_event = factories.audit_event.create(
            user=actor, event_type=AuditEventType.USER_MANAGEMENT, data=event.model_dump(mode="json")
        )

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        expected_links = {
            f"/deliver/admin/user/details/?id={actor.id}": "actor@example.com",
            f"/deliver/admin/user/details/?id={target_user.id}": "target@example.com",
            f"/deliver/admin/organisation/details/?id={organisation.id}": "Test Organisation",
            f"/deliver/admin/grant/details/?id={grant.id}": "Test Grant",
            f"/deliver/admin/grantrecipient/details/?id={grant_recipient.id}": "Test Organisation (Test Grant)",
            f"/deliver/admin/invitation/details/?id={invitation.id}": "invited@example.com",
        }
        for href, label in expected_links.items():
            link = soup.find("a", href=href)
            assert link is not None
            assert link.get_text(strip=True) == label

        assert get_summary_list_value_by_key(soup, "Permissions").get_text(strip=True) == "data-provider"
        assert get_summary_list_value_by_key(soup, "Resulting permissions").get_text(strip=True) == (
            "data-provider, member"
        )
        assert get_summary_list_value_by_key(soup, "Action").get_text(strip=True) == "permissions_added"
        assert soup.find("pre") is None

    def test_user_management_event_annotates_missing_entity_as_deleted(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        actor = factories.user.create()
        missing_organisation_id = uuid4()
        event = UserPermissionsAdded(
            user_id=actor.id,
            target_user_id=factories.user.create().id,
            organisation_id=missing_organisation_id,
            grant_id=None,
            grant_recipient_id=None,
            permissions=[RoleEnum.MEMBER],
            resulting_permissions=[RoleEnum.MEMBER],
        )
        audit_event = factories.audit_event.create(
            user=actor, event_type=AuditEventType.USER_MANAGEMENT, data=event.model_dump(mode="json")
        )

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        organisation_value = get_summary_list_value_by_key(soup, "Organisation")
        assert organisation_value.get_text(strip=True) == f"{missing_organisation_id} (deleted)"
        assert organisation_value.find("a") is None
        assert get_summary_list_value_by_key(soup, "Grant recipient").get_text(strip=True) == "—"

    def test_displays_database_model_change_with_entity_links(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        actor = factories.user.create(email="actor@example.com")
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(name="Report", grant=grant, created_by=actor)
        event = create_database_model_change_for_create(collection, actor)
        audit_event = factories.audit_event.create(user=actor, data=event.model_dump(mode="json"))

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        collection_links = soup.find_all("a", href=f"/deliver/admin/collection/details/?id={collection.id}")
        assert [link.get_text(strip=True) for link in collection_links] == [
            "Report (Test Grant)",
            "Report (Test Grant)",
        ]
        grant_link = soup.find("a", href=f"/deliver/admin/grant/details/?id={grant.id}")
        assert grant_link.get_text(strip=True) == "Test Grant"
        actor_links = soup.find_all("a", href=f"/deliver/admin/user/details/?id={actor.id}")
        assert [link.get_text(strip=True) for link in actor_links] == ["actor@example.com", "actor@example.com"]
        assert soup.find("dt", string="Name").find_next_sibling("dd").get_text(strip=True) == "Report"
        assert soup.find("pre") is None

    def test_displays_update_event_with_old_and_new_values(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        actor = factories.user.create()
        grant = factories.grant.create(name="Old Name")
        db_session.refresh(grant)
        grant.name = "New Name"
        event = create_database_model_change_for_update(grant, actor)
        db_session.commit()
        audit_event = factories.audit_event.create(user=actor, data=event.model_dump(mode="json"))

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.find("dt", string="Name").find_next_sibling("dd").get_text(strip=True) == "Old Name → New Name"
        model_link = soup.find("a", href=f"/deliver/admin/grant/details/?id={grant.id}")
        assert model_link.get_text(strip=True) == "New Name"

    def test_displays_system_event_with_context(self, authenticated_platform_admin_client, factories, db_session):
        actor = factories.user.create()
        target_user = factories.user.create(email="target@example.com")
        organisation = factories.organisation.create(name="Test Organisation")
        user_role = factories.user_role.create(
            user=target_user, organisation=organisation, permissions=[RoleEnum.ADMIN]
        )
        reason = "GOV.UK Notify callback indicated permanent delivery failure"
        event = create_system_event_for_delete(
            user_role, actor, context={"notification_id": str(uuid4()), "reason": reason}
        )
        user_role_id = user_role.id
        db_session.delete(user_role)
        db_session.commit()
        audit_event = factories.audit_event.create(
            user=actor, event_type=AuditEventType.SYSTEM, data=event.model_dump(mode="json")
        )

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        model_value = soup.find("dt", string="Model").find_next_sibling("dd")
        assert model_value.get_text(strip=True) == f"{user_role_id} (deleted)"
        assert soup.find("dt", string="Reason").find_next_sibling("dd").get_text(strip=True) == reason
        target_user_link = soup.find("a", href=f"/deliver/admin/user/details/?id={target_user.id}")
        assert target_user_link.get_text(strip=True) == "target@example.com"
        organisation_link = soup.find("a", href=f"/deliver/admin/organisation/details/?id={organisation.id}")
        assert organisation_link.get_text(strip=True) == "Test Organisation"

    def test_edit_route_not_available(self, authenticated_platform_admin_client, factories, db_session):
        audit_event = factories.audit_event.create()

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/edit/?id={audit_event.id}")
        assert response.status_code in (302, 404)

    def test_delete_route_not_available(self, authenticated_platform_admin_client, factories, db_session):
        audit_event = factories.audit_event.create()

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/auditevent/delete/",
            data={"id": str(audit_event.id)},
        )
        assert response.status_code in (302, 404)

    def test_filter_by_event_type(self, authenticated_platform_admin_client, factories, db_session):
        user = factories.user.create()
        factories.audit_event.create(user=user)

        response = authenticated_platform_admin_client.get("/deliver/admin/auditevent/?flt0_0=PLATFORM_ADMIN_DB_EVENT")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        table = soup.find("table")
        table_text = table.get_text()
        assert "platform-admin-db-event" in table_text

    def test_search_combined_with_filter_runs_against_enum_event_type(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        organisation = factories.organisation.create(external_id="E06000043", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(organisation=organisation)
        audit_event = factories.audit_event.create(
            data={
                "model_class": "GrantRecipient",
                "action": "update",
                "model_id": str(grant_recipient.id),
                "changes": {},
            },
        )

        response = authenticated_platform_admin_client.get(
            "/deliver/admin/auditevent/?search=platform-admin&flt0_10=GrantRecipient"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        table = soup.find("table")
        assert table is not None

        rows = table.find("tbody").find_all("tr")
        assert len(rows) == 1

        row_text = rows[0].get_text()
        assert audit_event.user.email in row_text
        assert "GrantRecipient" in row_text
        assert "update" in row_text
        assert str(audit_event.id) in str(rows[0])


class TestAdminAuditTracking:
    def test_updating_user_creates_audit_event(self, authenticated_platform_admin_client, factories, db_session):
        user = factories.user.create(name="Original Name")
        db_session.commit()

        initial_audit_count = db_session.query(AuditEvent).count()

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/user/edit/?id={user.id}",
            data={
                "name": "Updated Name",
                "email": user.email,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        final_audit_count = db_session.query(AuditEvent).count()
        assert final_audit_count == initial_audit_count + 1

        audit_event = db_session.query(AuditEvent).order_by(AuditEvent.created_at_utc.desc()).first()
        assert audit_event.event_type == AuditEventType.PLATFORM_ADMIN_DB_EVENT
        assert audit_event.data["model_class"] == "User"
        assert audit_event.data["action"] == "update"
        assert audit_event.data["changes"]["name"]["old"] == "Original Name"
        assert audit_event.data["changes"]["name"]["new"] == "Updated Name"

    def test_updating_without_changes_does_not_create_audit_event(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        user = factories.user.create(name="Same Name")
        db_session.commit()

        initial_audit_count = db_session.query(AuditEvent).count()

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/user/edit/?id={user.id}",
            data={
                "name": user.name,
                "email": user.email,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        final_audit_count = db_session.query(AuditEvent).count()
        assert final_audit_count == initial_audit_count

    def test_audit_event_records_user_who_made_change(self, authenticated_platform_admin_client, factories, db_session):
        user = factories.user.create(name="Test User")
        db_session.commit()

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/user/edit/?id={user.id}",
            data={
                "name": "Changed Name",
                "email": user.email,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        audit_event = db_session.query(AuditEvent).order_by(AuditEvent.created_at_utc.desc()).first()
        assert audit_event.user_id == authenticated_platform_admin_client.user.id
        assert audit_event.user.email == authenticated_platform_admin_client.user.email
