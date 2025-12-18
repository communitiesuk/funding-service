import pytest
from bs4 import BeautifulSoup

from app.common.data.models_audit import AuditEvent
from app.common.data.types import AuditEventType
from tests.utils import get_h1_text


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
        audit_event = factories.audit_event.create(
            data={
                "model_class": "Grant",
                "action": "update",
                "model_id": "123e4567-e89b-12d3-a456-426614174000",
                "changes": {"name": {"old": "Old Name", "new": "New Name"}},
            },
        )

        response = authenticated_platform_admin_client.get(f"/deliver/admin/auditevent/details/?id={audit_event.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        page_text = soup.get_text()
        assert "Grant" in page_text
        assert "update" in page_text
        assert "Old Name" in page_text
        assert "New Name" in page_text

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
