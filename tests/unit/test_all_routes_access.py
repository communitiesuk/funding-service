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
    "developers.access.grants_list",
    "developers.deliver.grant_developers",
    "developers.deliver.setup_collection",
    "developers.deliver.manage_collection_tasks",
    "developers.deliver.manage_collection",
    "developers.deliver.add_section",
    "developers.deliver.list_sections",
    "developers.deliver.move_section",
    "developers.deliver.move_form",
    "developers.deliver.manage_form_questions",
    "developers.deliver.manage_section",
    "developers.deliver.add_form",
    "developers.deliver.manage_form",
    "developers.deliver.choose_question_type",
    "developers.deliver.add_question",
    "developers.deliver.move_question",
    "developers.deliver.edit_question",
    "developers.deliver.add_question_condition_select_question",
    "developers.deliver.add_question_condition",
    "developers.deliver.edit_question_condition",
    "developers.deliver.submission_tasklist",
    "developers.deliver.ask_a_question",
    "developers.deliver.check_your_answers",
    "developers.deliver.add_question_validation",
    "developers.deliver.edit_question_validation",
    "developers.deliver.list_submissions_for_collection",
    "developers.deliver.export_submissions_for_collection",
    "developers.deliver.manage_submission",
    "deliver_grant_funding.grant_setup_intro",
    "deliver_grant_funding.grant_setup_ggis",
    "deliver_grant_funding.grant_setup_ggis_required_info",
    "deliver_grant_funding.grant_setup_name",
    "deliver_grant_funding.grant_setup_description",
    "deliver_grant_funding.grant_setup_contact",
    "deliver_grant_funding.grant_setup_check_your_answers",
    "deliver_grant_funding.add_user_to_grant",
    "deliver_grant_funding.grant_change_ggis",
]
routes_with_expected_grant_admin_only_access = [
    "deliver_grant_funding.grant_change_name",
    "deliver_grant_funding.grant_change_description",
    "deliver_grant_funding.grant_change_contact",
    "deliver_grant_funding.set_up_report",
]
routes_with_expected_member_only_access = [
    "deliver_grant_funding.list_users_for_grant",
    "deliver_grant_funding.grant_details",
    "deliver_grant_funding.list_reports",
]
routes_with_expected_access_grant_funding_logged_in_access = [
    "developers.access.start_submission_redirect",
    "developers.access.submission_tasklist",
    "developers.access.ask_a_question",
    "developers.access.check_your_answers",
    "developers.access.collection_confirmation",
]

routes_with_expected_is_mhclg_user_access = ["deliver_grant_funding.list_grants"]
routes_with_no_expected_access_restrictions = [
    "developers.access.grant_details",
    "auth.request_a_link_to_sign_in",
    "auth.check_email",
    "auth.claim_magic_link",
    "auth.sso_sign_in",
    "auth.sso_get_token",
    "auth.sign_out",
    "deliver_grant_funding.return_from_test_submission",  # the target endpoints have auth
    "static",
    "healthcheck.healthcheck",
    "index",
]


def test_accessibility_for_user_role_to_each_endpoint(app):
    for rule in app.url_map.iter_rules():
        decorators = _get_decorators(app.view_functions[rule.endpoint])
        if rule.endpoint in routes_with_expected_platform_admin_only_access:
            assert "@is_platform_admin" in decorators
        elif rule.endpoint in routes_with_expected_grant_admin_only_access:
            assert "@has_grant_role(RoleEnum.ADMIN)" in decorators
        elif rule.endpoint in routes_with_expected_member_only_access:
            assert "@has_grant_role(RoleEnum.MEMBER)" in decorators
        elif rule.endpoint in routes_with_expected_is_mhclg_user_access:
            assert "@is_mhclg_user" in decorators
        # todo: this will be the access grant funding routes where the user is logged in
        #       and will likely have access through their org, this should be updated as part of that work
        elif rule.endpoint in routes_with_expected_access_grant_funding_logged_in_access:
            assert "@access_grant_funding_login_required" in decorators
        elif rule.endpoint in routes_with_no_expected_access_restrictions:
            # If route is expected to be unauthenticated, check it doesn't have any auth decorators
            assert not any(decorator in all_auth_annotations for decorator in decorators)

        else:
            raise pytest.fail(f"Unexpected endpoint {rule.endpoint}. Add this to the expected_route_access mapping.")  # ty: ignore[call-non-callable]


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
