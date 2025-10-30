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
    "@is_deliver_grant_funding_user",
    "@has_deliver_grant_role(RoleEnum.MEMBER)",
    "@has_deliver_grant_role(RoleEnum.ADMIN)",
    "@is_platform_admin",
]

routes_with_expected_platform_admin_only_access = [
    "developers.access.grants_list",
    "developers.deliver.grant_developers",
    "deliver_grant_funding.grant_change_ggis",
]
routes_with_expected_deliver_org_admin_only_access = [
    "deliver_grant_funding.grant_setup_intro",
    "deliver_grant_funding.grant_setup_ggis",
    "deliver_grant_funding.grant_setup_ggis_required_info",
    "deliver_grant_funding.grant_setup_name",
    "deliver_grant_funding.grant_setup_description",
    "deliver_grant_funding.grant_setup_contact",
    "deliver_grant_funding.grant_setup_check_your_answers",
]
routes_with_expected_grant_admin_only_access = [
    "deliver_grant_funding.add_user_to_grant",
    "deliver_grant_funding.grant_change_name",
    "deliver_grant_funding.grant_change_description",
    "deliver_grant_funding.grant_change_contact",
    "deliver_grant_funding.set_up_report",
    "deliver_grant_funding.change_report_name",
    "deliver_grant_funding.add_task",
    "deliver_grant_funding.change_form_name",
    "deliver_grant_funding.change_group_name",
    "deliver_grant_funding.change_group_display_options",
    "deliver_grant_funding.change_group_add_another_options",
    "deliver_grant_funding.change_group_add_another_summary",
    "deliver_grant_funding.move_task",
    "deliver_grant_funding.move_component",
    "deliver_grant_funding.choose_question_type",
    "deliver_grant_funding.add_question",
    "deliver_grant_funding.add_question_group_name",
    "deliver_grant_funding.add_question_group_display_options",
    "deliver_grant_funding.select_context_source",
    "deliver_grant_funding.select_context_source_question",
    "deliver_grant_funding.edit_question",
    "deliver_grant_funding.manage_guidance",
    "deliver_grant_funding.manage_add_another_guidance",
    "deliver_grant_funding.add_question_condition_select_question",
    "deliver_grant_funding.add_question_condition",
    "deliver_grant_funding.edit_question_condition",
    "deliver_grant_funding.add_question_validation",
    "deliver_grant_funding.edit_question_validation",
]
routes_with_expected_member_only_access = [
    "deliver_grant_funding.list_users_for_grant",
    "deliver_grant_funding.grant_details",
    "deliver_grant_funding.list_reports",
    "deliver_grant_funding.list_report_tasks",
    "deliver_grant_funding.list_task_questions",
    "deliver_grant_funding.list_group_questions",
    "deliver_grant_funding.ask_a_question",
    "deliver_grant_funding.submission_tasklist",
    "deliver_grant_funding.check_your_answers",
    "deliver_grant_funding.list_submissions",
    "deliver_grant_funding.view_submission",
    "deliver_grant_funding.export_report_submissions",
]

routes_with_expected_access_grant_funding_logged_in_access = [
    "developers.access.start_submission_redirect",
    "developers.access.submission_tasklist",
    "developers.access.ask_a_question",
    "developers.access.check_your_answers",
    "developers.access.collection_confirmation",
]

routes_with_expected_is_deliver_grant_funding_user_access = [
    "deliver_grant_funding.list_grants",
]
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
    # \/ authorisation done within the endpoint, to avoid redirects+session hijacking \/
    "deliver_grant_funding.api.preview_guidance",
    "xgovuk_flask_admin.static",
]
routes_with_access_controlled_by_flask_admin = [
    "platform_admin.index",
    "platform_admin.static",
    "user.action_view",
    "user.ajax_lookup",
    "user.ajax_update",
    "user.create_view",
    "user.delete_view",
    "user.details_view",
    "user.edit_view",
    "user.export",
    "user.index_view",
    "organisation.action_view",
    "organisation.ajax_lookup",
    "organisation.ajax_update",
    "organisation.create_view",
    "organisation.delete_view",
    "organisation.details_view",
    "organisation.edit_view",
    "organisation.export",
    "organisation.index_view",
    "userrole.action_view",
    "userrole.ajax_lookup",
    "userrole.ajax_update",
    "userrole.create_view",
    "userrole.delete_view",
    "userrole.details_view",
    "userrole.edit_view",
    "userrole.export",
    "userrole.index_view",
    "grant.action_view",
    "grant.ajax_lookup",
    "grant.ajax_update",
    "grant.create_view",
    "grant.delete_view",
    "grant.details_view",
    "grant.edit_view",
    "grant.export",
    "grant.index_view",
    "invitation.action_view",
    "invitation.ajax_lookup",
    "invitation.ajax_update",
    "invitation.create_view",
    "invitation.delete_view",
    "invitation.details_view",
    "invitation.edit_view",
    "invitation.export",
    "invitation.index_view",
    "collection.action_view",
    "collection.ajax_lookup",
    "collection.ajax_update",
    "collection.create_view",
    "collection.delete_view",
    "collection.details_view",
    "collection.edit_view",
    "collection.export",
    "collection.index_view",
    "grantrecipient.action_view",
    "grantrecipient.ajax_lookup",
    "grantrecipient.ajax_update",
    "grantrecipient.create_view",
    "grantrecipient.delete_view",
    "grantrecipient.details_view",
    "grantrecipient.edit_view",
    "grantrecipient.export",
    "grantrecipient.index_view",
    "reporting_lifecycle.index",
    "reporting_lifecycle.tasklist",
    "reporting_lifecycle.make_live",
    "reporting_lifecycle.set_up_organisations",
    "reporting_lifecycle.set_up_grant_recipients",
]


def test_accessibility_for_user_role_to_each_endpoint(app):
    for rule in app.url_map.iter_rules():
        decorators = _get_decorators(app.view_functions[rule.endpoint])
        if rule.endpoint in routes_with_expected_platform_admin_only_access:
            assert "@is_platform_admin" in decorators
        elif rule.endpoint in routes_with_expected_deliver_org_admin_only_access:
            assert "@is_deliver_org_admin" in decorators
        elif rule.endpoint in routes_with_expected_grant_admin_only_access:
            assert "@has_deliver_grant_role(RoleEnum.ADMIN)" in decorators
        elif rule.endpoint in routes_with_expected_member_only_access:
            assert "@has_deliver_grant_role(RoleEnum.MEMBER)" in decorators
        elif rule.endpoint in routes_with_expected_is_deliver_grant_funding_user_access:
            assert "@is_deliver_grant_funding_user" in decorators
        # todo: this will be the access grant funding routes where the user is logged in
        #       and will likely have access through their org, this should be updated as part of that work
        elif rule.endpoint in routes_with_expected_access_grant_funding_logged_in_access:
            assert "@access_grant_funding_login_required" in decorators
        elif rule.endpoint in routes_with_no_expected_access_restrictions:
            # If route is expected to be unauthenticated, check it doesn't have any auth decorators
            assert not any(decorator in all_auth_annotations for decorator in decorators)
        elif rule.endpoint in routes_with_access_controlled_by_flask_admin:
            # authentication of flask-admin routes is controlled by FlaskAdminPlatformAdminAccessibleMixin
            pass
        else:
            raise pytest.fail(f"Unexpected endpoint {rule.endpoint}. Add this to the expected_route_access mapping.")  # ty: ignore[call-non-callable]


def test_routes_list_is_valid(app):
    all_declared_routes_in_test = (
        routes_with_no_expected_access_restrictions
        + routes_with_expected_is_deliver_grant_funding_user_access
        + routes_with_expected_member_only_access
        + routes_with_expected_grant_admin_only_access
        + routes_with_expected_platform_admin_only_access
        + routes_with_access_controlled_by_flask_admin
    )

    all_routes_in_app = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert set(all_declared_routes_in_test) - set(all_routes_in_app) == set()
