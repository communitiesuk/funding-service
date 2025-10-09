import pytest


class TestFlaskAdminAccess:
    """Test that Flask-Admin pages are only accessible to platform admin users."""

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
        ],
    )
    def test_admin_index_denied_for_non_platform_admin(self, client_fixture, expected_code, request):
        """Non-platform admin authenticated users cannot access the admin index page."""
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/")
        assert response.status_code == expected_code

    def test_admin_index_denied_for_anonymous(self, anonymous_client):
        """Anonymous users cannot access the admin index page."""
        response = anonymous_client.get("/deliver/admin/")
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
        ],
    )
    def test_admin_user_list_denied_for_non_platform_admin(self, client_fixture, expected_code, request):
        """Non-platform admin authenticated users cannot access the user list page."""
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/user/")
        assert response.status_code == expected_code

    def test_admin_user_list_denied_for_anonymous(self, anonymous_client):
        """Anonymous users cannot access the user list page."""
        response = anonymous_client.get("/deliver/admin/user/")
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
        ],
    )
    def test_admin_user_detail_denied_for_non_platform_admin(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        """Non-platform admin authenticated users cannot access user detail pages."""
        client = request.getfixturevalue(client_fixture)
        user = factories.user.create()
        db_session.commit()

        response = client.get(f"/deliver/admin/user/details/?id={user.id}", follow_redirects=True)
        assert response.status_code == expected_code

    def test_admin_user_detail_denied_for_anonymous(self, anonymous_client, factories, db_session):
        """Anonymous users cannot access user detail pages."""
        user = factories.user.create()
        db_session.commit()

        response = anonymous_client.get(f"/deliver/admin/user/details/?id={user.id}")
        assert response.status_code == 403
