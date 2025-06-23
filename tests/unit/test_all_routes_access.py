import inspect

import pytest


def _get_decorators(func):
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        return []
    lines = src.splitlines()
    return [line.strip() for line in lines if line.strip().startswith("@")]


all_auth_annotations = [
    "@login_required",
    "@mhclg_login_required",
    "@has_grant_role(RoleEnum.MEMBER)",
    "@has_grant_role(RoleEnum.ADMIN)",
    "@platform_admin_role_required",
]
routes_with_expected_platform_admin_only_access = [
    "developers_dgf.grant_developers",
    "developers_dgf.grant_developers_collections",
    "developers_dgf.setup_collection",
    "developers_dgf.manage_collection",
    "developers_dgf.edit_collection",
    "developers_dgf.add_section",
    "developers_dgf.list_sections",
    "developers_dgf.move_section",
    "developers_dgf.manage_section",
    "developers_dgf.move_form",
    "developers_dgf.manage_form",
    "developers_dgf.edit_section",
    "developers_dgf.add_form",
    "developers_dgf.edit_form",
    "developers_dgf.choose_question_type",
    "developers_dgf.add_question",
    "developers_dgf.move_question",
    "developers_dgf.edit_question",
    "developers_dgf.add_question_condition_select_question",
    "developers_dgf.add_question_condition",
    "developers_dgf.submission_tasklist",
    "developers_dgf.collection_confirmation",
    "developers_dgf.ask_a_question",
    "developers_dgf.check_your_answers",
    "developers_dgf.add_question_validation",
    "developers_dgf.list_submissions_for_collection",
    "developers_dgf.manage_submission",
    "deliver_grant_funding.grant_setup_intro",
    "deliver_grant_funding.grant_setup_ggis",
    "deliver_grant_funding.grant_setup_name",
    "deliver_grant_funding.grant_setup_description",
    "deliver_grant_funding.grant_setup_contact",
    "deliver_grant_funding.grant_setup_check_your_answers",
    "deliver_grant_funding.grant_setup_confirmation",
    "deliver_grant_funding.add_user_to_grant",
    "deliver_grant_funding.grant_change_ggis",
    "deliver_grant_funding.grant_change_name",
    "deliver_grant_funding.grant_change_description",
    "deliver_grant_funding.grant_change_contact",
]
routes_with_expected_grant_admin_only_access = []
routes_with_expected_member_only_access = [
    "deliver_grant_funding.list_users_for_grant",
    "deliver_grant_funding.view_grant",
    "deliver_grant_funding.grant_details",
]

routes_with_expected_mhclg_login_required_access = ["deliver_grant_funding.list_grants"]
routes_with_no_expected_access_restrictions = [
    "auth.request_a_link_to_sign_in",
    "auth.check_email",
    "auth.claim_magic_link",
    "auth.sso_sign_in",
    "auth.sso_get_token",
    "auth.sign_out",
    "static",
    "healthcheck.healthcheck",
    "index",
    "developers_agf.index",
]


def test_accessibility_for_user_role_to_each_endpoint(app):
    for rule in app.url_map.iter_rules():
        decorators = _get_decorators(app.view_functions[rule.endpoint])
        if rule.endpoint in routes_with_expected_platform_admin_only_access:
            assert "@platform_admin_role_required" in decorators
        elif rule.endpoint in routes_with_expected_member_only_access:
            assert "@has_grant_role(RoleEnum.MEMBER)" in decorators
        elif rule.endpoint in routes_with_expected_mhclg_login_required_access:
            assert "@mhclg_login_required" in decorators
        elif rule.endpoint in routes_with_no_expected_access_restrictions:
            # If route is expected to be unauthenticated, check it doesn't have any auth decorators
            assert not any(decorator in all_auth_annotations for decorator in decorators)

        else:
            pytest.fail(f"Unexpected endpoint {rule.endpoint}. Add this to the expected_route_access mapping.")


def test_routes_list_is_valid(app):
    all_declared_routes_in_test = (
        routes_with_no_expected_access_restrictions
        + routes_with_expected_mhclg_login_required_access
        + routes_with_expected_member_only_access
        + routes_with_expected_grant_admin_only_access
        + routes_with_expected_platform_admin_only_access
    )

    all_routes_in_app = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert set(all_declared_routes_in_test) - set(all_routes_in_app) == set()
