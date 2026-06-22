import pytest

from app.common.data.types import TraceLevelEnum
from app.common.helpers.request_tracing import (
    REQUEST_TRACING_COOKIE_NAME,
    REQUEST_TRACING_TTL,
    decode_levels,
    encode_levels,
)


def _set_cookie_to_levels(client, app, levels: list[TraceLevelEnum]) -> None:
    token = encode_levels(levels, app.config["SECRET_KEY"])
    client.set_cookie(REQUEST_TRACING_COOKIE_NAME, token, domain="funding.communities.gov.localhost", max_age=900)


def _force_trace_cookie_from_response(response) -> str:
    return next(h for h in response.headers.getlist("Set-Cookie") if h.startswith(f"{REQUEST_TRACING_COOKIE_NAME}="))


def _is_deleted_cookie(cookie: str) -> bool:
    return "Max-Age=0" in cookie or "Expires=Thu, 01 Jan 1970" in cookie


class TestDeveloperToolsAdminAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_developer_tools_page_access(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/developer-tools/")
        assert response.status_code == expected_code


class TestDeveloperToolsAdminPage:
    def test_get_renders_form_with_a_choice_per_tracing_level(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/developer-tools/")
        assert response.status_code == 200
        assert "Developer tools" in response.text
        assert "Request tracing" in response.text
        for level in TraceLevelEnum:
            assert level.value.capitalize() in response.text

    def test_post_with_levels_sets_signed_cookie_with_full_ttl(self, authenticated_platform_admin_client, app):
        selected_levels = {TraceLevelEnum.TRACE, TraceLevelEnum.PROFILE}
        response = authenticated_platform_admin_client.post(
            "/deliver/admin/developer-tools/",
            data={"levels": sorted(level.value for level in selected_levels)},
        )
        assert response.status_code == 302

        cookie = _force_trace_cookie_from_response(response)
        assert f"Max-Age={REQUEST_TRACING_TTL}" in cookie

        token = cookie.split("=", 1)[1].split(";", 1)[0]
        assert set(decode_levels(token, app.config["SECRET_KEY"])) == selected_levels

    def test_post_with_no_levels_deletes_cookie(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.post("/deliver/admin/developer-tools/", data={"levels": []})
        assert response.status_code == 302
        cookie = _force_trace_cookie_from_response(response)
        assert "Max-Age=0" in cookie or "Expires=Thu, 01 Jan 1970" in cookie

    def test_stop_endpoint_deletes_cookie(self, authenticated_platform_admin_client, app):
        _set_cookie_to_levels(authenticated_platform_admin_client, app, [TraceLevelEnum.TRACE])
        response = authenticated_platform_admin_client.post("/deliver/admin/developer-tools/stop")
        assert response.status_code == 302
        cookie = _force_trace_cookie_from_response(response)
        assert "Max-Age=0" in cookie or "Expires=Thu, 01 Jan 1970" in cookie


class TestRequestTracingBanner:
    @pytest.mark.freeze_time("2026-01-01 12:00:00")
    def test_banner_appears_when_cookie_set(self, authenticated_platform_admin_client, app):
        _set_cookie_to_levels(authenticated_platform_admin_client, app, [TraceLevelEnum.TRACE])
        response = authenticated_platform_admin_client.get("/deliver/grants")
        assert response.status_code == 200
        assert "Stop tracing" in response.text
        assert ": sentry tracing" in response.text

    @pytest.mark.freeze_time("2026-01-01 12:00:00")
    def test_banner_lists_all_enabled_levels_comma_separated(self, authenticated_platform_admin_client, app):
        _set_cookie_to_levels(authenticated_platform_admin_client, app, [TraceLevelEnum.TRACE, TraceLevelEnum.PROFILE])
        response = authenticated_platform_admin_client.get("/deliver/grants")
        expected_label = ": sentry tracing, sentry profiling"
        assert expected_label in response.text

    @pytest.mark.freeze_time("2026-01-01 12:00:00")
    def test_banner_shows_time_remaining_until_cookie_expiry(self, authenticated_platform_admin_client, app):
        _set_cookie_to_levels(authenticated_platform_admin_client, app, [TraceLevelEnum.TRACE])
        response = authenticated_platform_admin_client.get("/deliver/grants")
        assert "enabled for 15m 00s" in response.text

    @pytest.mark.freeze_time("2026-01-01 12:00:00")
    def test_banner_absent_when_no_cookie(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/grants")
        assert response.status_code == 200
        assert "Stop tracing" not in response.text
