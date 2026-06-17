import pytest


class TestFeatureFlagsAdminAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 200),
            ("authenticated_platform_data_analyst_client", 200),
            ("authenticated_platform_member_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_feature_flags_page_access(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/feature-flags/")
        assert response.status_code == expected_code


class TestFeatureFlagsPage:
    def test_get_renders_all_flags(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/feature-flags/")
        assert response.status_code == 200
        assert "Feature flags" in response.text
        assert "PRE_AWARD" in response.text
        assert "NEW_CONTEXT_SOURCES" in response.text
        assert "NEW_CHANGE_REQUESTS" in response.text
        assert "pre-award functionality for grants" in response.text
        assert "context sources for referencing data" in response.text
        assert "new change request workflow" in response.text

    def test_only_renders_change_links_for_session_flags(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/feature-flags/")
        assert "/deliver/admin/feature-flags/toggle/NEW_CHANGE_REQUESTS" in response.text
        assert "/deliver/admin/feature-flags/toggle/PRE_AWARD" not in response.text


class TestToggleFeatureFlag:
    def test_get_toggle_page_for_session_flag(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/feature-flags/toggle/NEW_CHANGE_REQUESTS")
        assert response.status_code == 200
        assert "NEW_CHANGE_REQUESTS" in response.text

    def test_post_toggle_enables_session_flag(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.post(
            "/deliver/admin/feature-flags/toggle/NEW_CHANGE_REQUESTS",
            data={"enabled": "on"},
        )
        assert response.status_code == 302

        with authenticated_platform_admin_client.session_transaction() as sess:
            assert "NEW_CHANGE_REQUESTS" in sess

    def test_post_toggle_disables_session_flag(self, authenticated_platform_admin_client):
        with authenticated_platform_admin_client.session_transaction() as sess:
            sess["NEW_CHANGE_REQUESTS"] = "on"

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/feature-flags/toggle/NEW_CHANGE_REQUESTS",
            data={"enabled": "off"},
        )
        assert response.status_code == 302

        with authenticated_platform_admin_client.session_transaction() as sess:
            assert "NEW_CHANGE_REQUESTS" not in sess

    def test_toggle_non_global_flag_returns_404(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/feature-flags/toggle/PRE_AWARD")
        assert response.status_code == 404

    def test_toggle_nonexistent_flag_returns_404(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/feature-flags/toggle/DOES_NOT_EXIST")
        assert response.status_code == 404
