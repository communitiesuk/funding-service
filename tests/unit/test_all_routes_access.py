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
    "@is_mhclg_user",
    "@has_grant_role(RoleEnum.MEMBER)",
    "@has_grant_role(RoleEnum.ADMIN)",
    "@is_platform_admin",
]
routes_with_expected_platform_admin_only_access = [
    "developers.grant_developers",
    "developers.grant_developers_collections",
    "developers.setup_collection",
    "developers.manage_collection",
    "developers.edit_collection",
    "developers.add_section",
    "developers.list_sections",
    "developers.move_section",
    "developers.manage_section",
    "developers.move_form",
    "developers.manage_form",
    "developers.edit_section",
    "developers.add_form",
    "developers.edit_form",
    "developers.choose_question_type",
    "developers.add_question",
    "developers.move_question",
    "developers.edit_question",
    "developers.add_question_condition_select_question",
    "developers.add_question_condition",
    "developers.submission_tasklist",
    "developers.collection_confirmation",
    "developers.ask_a_question",
    "developers.check_your_answers",
    "developers.add_question_validation",
    "developers.list_submissions_for_collection",
    "developers.manage_submission",
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

routes_with_expected_is_mhclg_user_access = ["deliver_grant_funding.list_grants"]
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
]


def test_accessibility_for_user_role_to_each_endpoint(app):
    for rule in app.url_map.iter_rules():
        decorators = _get_decorators(app.view_functions[rule.endpoint])
        if rule.endpoint in routes_with_expected_platform_admin_only_access:
            assert "@is_platform_admin" in decorators
        elif rule.endpoint in routes_with_expected_member_only_access:
            assert "@has_grant_role(RoleEnum.MEMBER)" in decorators
        elif rule.endpoint in routes_with_expected_is_mhclg_user_access:
            assert "@is_mhclg_user" in decorators
        elif rule.endpoint in routes_with_no_expected_access_restrictions:
            # If route is expected to be unauthenticated, check it doesn't have any auth decorators
            assert not any(decorator in all_auth_annotations for decorator in decorators)

        else:
            pytest.fail(f"Unexpected endpoint {rule.endpoint}. Add this to the expected_route_access mapping.")


def test_routes_list_is_valid(app):
    all_declared_routes_in_test = (
        routes_with_no_expected_access_restrictions
        + routes_with_expected_is_mhclg_user_access
        + routes_with_expected_member_only_access
        + routes_with_expected_grant_admin_only_access
        + routes_with_expected_platform_admin_only_access
    )

    all_routes_in_app = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert set(all_declared_routes_in_test) - set(all_routes_in_app) == set()
