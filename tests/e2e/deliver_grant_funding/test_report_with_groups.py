import uuid

import pytest
from playwright.sync_api import Page, expect

from app import NumberTypeEnum
from app.common.data.types import (
    GroupDisplayOptions,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import (
    IsYes,
)
from tests.e2e.access_grant_funding.pages import AccessGrantPage, AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import (
    TEST_DATA_TO_BE_SEEDED,
    DeliverGrantFundingUserType,
    e2e_user_configs,
)
from tests.e2e.dataclasses import (
    DataReferenceConfig,
    E2EManagedExpression,
    E2ETestUser,
    GuidanceText,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    ReportDict,
    SectionDict,
)
from tests.e2e.deliver_grant_funding.helpers import (
    complete_task,
    create_question_or_group,
    extract_uuid_from_url,
    navigate_to_report_sections_page,
    switch_user,
    task_check_your_answers,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDetailsPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AdminReportingLifecycleTasklistPage,
    DeliverTestGrantRecipientJourneyPage,
    GrantReportsPage,
    MarkAsOnboardingWithFundingServicePage,
    OverrideGrantRecipientCertifiersPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    RunnerTasklistPage,
    SetPrivacyPolicyPage,
    SetReportingDatesPage,
    SetUpDataProvidersPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
    ViewLockedReportPage,
)
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
)

report_with_groups: ReportDict = {
    "id": None,
    "name": f"E2E Report with all question types {str(uuid.uuid4())}",
    "require_certification": True,
    "allow_multi_submissions": False,
    "sections": [
        SectionDict(
            name="E2E first task - grouped questions",
            components=[
                QuestionDict(
                    type=QuestionDataType.YES_NO,
                    text="Do you want to show question groups?",
                    display_text="Do you want to show question groups?",
                    answers=[
                        QuestionResponse("Yes"),
                    ],
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="What number do you want to see in another section?",
                    display_text="What number do you want to see in another section?",
                    options=QuestionPresentationOptions(),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                    answers=[
                        QuestionResponse("100"),
                    ],
                ),
                QuestionGroupDict(
                    type="group",
                    text="This is a question group",
                    display_options=GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
                    guidance=GuidanceText(
                        heading="This is a guidance page heading for a group",
                        body_heading="Guidance subheading",
                        body_link_text="Design system link text",
                        body_link_url="https://design-system.service.gov.uk",
                        body_ul_items=["UL item one", "UL item two"],
                        body_ol_items=["OL item one", "OL item two"],
                    ),
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Do you want to show question groups?",
                        ),
                        evaluatable_expression=IsYes(subject_reference="q_00000000000000000000000000001234"),
                    ),
                    questions=[
                        QuestionDict(
                            type=QuestionDataType.TEXT_SINGLE_LINE,
                            text="Group Enter a single line of text",
                            display_text="Group Enter a single line of text",
                            answers=[QuestionResponse("E2E question text single line")],
                        ),
                        QuestionDict(
                            type=QuestionDataType.URL,
                            text="Group Enter a website address",
                            display_text="Group Enter a website address",
                            answers=[
                                QuestionResponse("https://gov.uk"),
                            ],
                        ),
                        QuestionDict(
                            type=QuestionDataType.EMAIL,
                            text="Group Enter an email address",
                            display_text="Group Enter an email address",
                            answers=[
                                QuestionResponse("group@example.com"),
                            ],
                        ),
                    ],
                ),
                QuestionDict(
                    type=QuestionDataType.TEXT_SINGLE_LINE,
                    text="Enter another single line of text",
                    display_text="Enter another single line of text",
                    answers=[QuestionResponse("E2E question text single line second answer")],
                ),
                QuestionGroupDict(
                    type="group",
                    text="Number questions with group validation",
                    display_options=GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Do you want to show question groups?",
                        ),
                        evaluatable_expression=IsYes(subject_reference="q_00000000000000000000000000001234"),
                    ),
                    validation=E2EManagedExpression(
                        evaluatable_expression=CustomExpression(
                            custom_expression="((ref1)) + ((ref2)) + ((ref3)) <= ((ref4))",
                            custom_message="The total of the three amounts must not exceed the allowed amount",
                        ),
                        expression_references={
                            "ref1": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="First number amount",
                            ),
                            "ref2": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="Second number amount",
                            ),
                            "ref3": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="Third number amount",
                            ),
                            "ref4": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="What number do you want to see in another section?",
                            ),
                        },
                    ),
                    questions=[
                        QuestionDict(
                            type=QuestionDataType.NUMBER,
                            text="First number amount",
                            display_text="First number amount",
                            options=QuestionPresentationOptions(),
                            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                            answers=[
                                QuestionResponse(
                                    "40", "Check First number amount (40)", expect_group_validation_error=True
                                ),
                                QuestionResponse("30"),
                            ],
                        ),
                        QuestionDict(
                            type=QuestionDataType.NUMBER,
                            text="Second number amount",
                            display_text="Second number amount",
                            options=QuestionPresentationOptions(),
                            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                            answers=[
                                QuestionResponse(
                                    "56", "Check Second number amount (56)", expect_group_validation_error=True
                                ),
                                QuestionResponse("30"),
                            ],
                        ),
                        QuestionDict(
                            type=QuestionDataType.NUMBER,
                            text="Third number amount",
                            display_text="Third number amount",
                            options=QuestionPresentationOptions(),
                            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                            answers=[
                                QuestionResponse(
                                    "45", "Check Third number amount (45)", expect_group_validation_error=True
                                ),
                                QuestionResponse("30"),
                            ],
                        ),
                    ],
                ),
                QuestionGroupDict(
                    type="group",
                    text="One question per page group",
                    display_options=GroupDisplayOptions.ONE_QUESTION_PER_PAGE,
                    questions=[
                        QuestionDict(
                            type=QuestionDataType.TEXT_SINGLE_LINE,
                            text="Second group Enter a single line of text",
                            display_text="Second group Enter a single line of text",
                            answers=[QuestionResponse("E2E question text single line group")],
                        ),
                        QuestionDict(
                            type=QuestionDataType.EMAIL,
                            text="Second group Enter an email address",
                            display_text="Second group Enter an email address",
                            answers=[
                                QuestionResponse("group2@example.com"),
                            ],
                        ),
                        QuestionGroupDict(
                            type="group",
                            text="Nested Group",
                            display_options=GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
                            questions=[
                                QuestionDict(
                                    type=QuestionDataType.TEXT_SINGLE_LINE,
                                    text="Nested group single line of text",
                                    display_text="Nested group single line of text",
                                    answers=[QuestionResponse("E2E question text single line nested group")],
                                ),
                                QuestionDict(
                                    type=QuestionDataType.EMAIL,
                                    text="Nested group Enter an email address",
                                    display_text="Nested group Enter an email address",
                                    answers=[
                                        QuestionResponse("nested_group@example.com"),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ],
}


def test_setup_grant_and_collection(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:

    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(seeded_e2e_grant["name"])

    # Go to Reports tab
    grant_reports_page = grant_dashboard_page.click_reports(seeded_e2e_grant["name"])

    # Add a new report
    add_report_page = grant_reports_page.click_add_report()
    new_report_name = report_with_groups["name"]
    add_report_page.fill_in_report_name(new_report_name)
    grant_reports_page = add_report_page.click_submit(seeded_e2e_grant["name"])
    grant_reports_page.check_report_exists(new_report_name)
    collection_id = None

    for section in report_with_groups["sections"]:
        # If it's the first section
        if not collection_id:
            add_section_page = grant_reports_page.click_add_section(
                report_name=new_report_name, grant_name=seeded_e2e_grant["name"]
            )
            # Extract collection_id from URL (e.g., /grant/<uuid>/reports/<uuid>/sections)
            collection_id = extract_uuid_from_url(page.url, r"/report/(?P<uuid>[a-f0-9-]+)")
            report_with_groups["id"] = uuid.UUID(collection_id)
        else:
            report_sections_page = navigate_to_report_sections_page(
                page, domain, seeded_e2e_grant["name"], new_report_name
            )
            add_section_page = report_sections_page.click_add_section()

        add_section_page.fill_in_section_name(section["name"])
        report_sections_page = add_section_page.click_add_section()
        report_sections_page.check_section_exists(section["name"])

        manage_section_page = report_sections_page.click_manage_section(section_name=section["name"])
        for question_to_test in section["components"]:
            create_question_or_group(question_to_test, manage_section_page)

    # Add grant team member
    grant_team_page = grant_reports_page.click_nav_grant_team()
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    add_grant_team_member_page.fill_in_user_email(grant_team_email)
    grant_team_page = add_grant_team_member_page.click_continue()

    # Switch to grant team member (claim invitation/userrole), then switch back to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    reporting_lifecycle_tasklist_page = AdminReportingLifecycleTasklistPage(
        page, domain, seeded_e2e_grant["id"], collection_id
    )
    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set up organisations")

    # TODO seed our e2e test organisation; note a shadow test org will be created automatically

    tsv_data = (
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"MHCLG-TEST-ORG\t{TEST_DATA_TO_BE_SEEDED['grant_recipient_org']}\tCentral Government\t\t\n"
    )
    set_up_orgs_page = SetUpOrganisationsPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_up_orgs_page.fill_organisations_tsv_data(tsv_data)
    set_up_orgs_page.click_set_up_organisations()

    reporting_lifecycle_tasklist_page.click_task("Set up grant recipients")
    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_up_grant_recipients_page.select_organisation(TEST_DATA_TO_BE_SEEDED["grant_recipient_org"])
    set_up_grant_recipients_page.click_set_up_grant_recipients()

    tsv_data = (
        f"organisation-name\tfull-name\temail-address\n{TEST_DATA_TO_BE_SEEDED['grant_recipient_org']}"
        f"\t{TEST_DATA_TO_BE_SEEDED['grant_recipient_user_name']}\t"
        f"{TEST_DATA_TO_BE_SEEDED['grant_recipient_user_email']}\n"
    )
    reporting_lifecycle_tasklist_page.click_task("Set up grant recipient data providers")
    setup_data_providers_page = SetUpDataProvidersPage(page, domain, seeded_e2e_grant["id"], collection_id)
    setup_data_providers_page.fill_users_tsv_data(tsv_data)
    setup_data_providers_page.click_set_up_users()

    reporting_lifecycle_tasklist_page.click_task("Override certifiers for this grant")
    override_certifiers_page = OverrideGrantRecipientCertifiersPage(page, domain, seeded_e2e_grant["id"], collection_id)
    override_certifiers_page.select_organisation(TEST_DATA_TO_BE_SEEDED["grant_recipient_org"])
    override_certifiers_page.complete_user_details(
        TEST_DATA_TO_BE_SEEDED["grant_recipient_user_name"], TEST_DATA_TO_BE_SEEDED["grant_recipient_user_email"]
    )
    override_certifiers_page.click_add_certifier()

    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set reporting dates")
    set_reporting_dates_page = SetReportingDatesPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_reporting_dates_page.set_dates_for_open_report()
    set_reporting_dates_page.click_save_dates(report_name=new_report_name)

    reporting_lifecycle_tasklist_page.click_task("Mark as onboarding with Funding Service")
    mark_as_onboarding_page = MarkAsOnboardingWithFundingServicePage(
        page, domain, seeded_e2e_grant["id"], collection_id
    )
    mark_as_onboarding_page.click_mark_as_onboarding()

    reporting_lifecycle_tasklist_page.click_task("Set privacy policy")
    set_privacy_policy_page = SetPrivacyPolicyPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_privacy_policy_page.fill_privacy_policy_markdown("https://www.gov.uk/help/privacy-notice")
    set_privacy_policy_page.click_save_privacy_policy()

    # Do this the admin way so we don't have to create grant team users (that's why the option is
    # greyed out in the tasklist at this point)
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, seeded_e2e_grant["id"])
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status("LIVE")
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status("OPEN")
    report_settings_page.click_save()

    # The report is now open and ready for submissions
    # TODO go on to login with the fsd-post-award user via magic link and complete the report


def test_preview_collection(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:
    """Grant team member previews and fills the collection."""
    assert report_with_groups["id"] is not None, "Setup test must run first"

    # Switch to grant team member
    switch_user(
        page,
        domain,
        e2e_test_secrets,
        DeliverGrantFundingUserType.GRANT_TEAM_MEMBER,
        TEST_DATA_TO_BE_SEEDED["grant_team_email"],
    )

    # Preview the report
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # This page can auto-redirect to the grant page; if it doesn't we should click the grant name.
    if all_grants_page.title.is_visible():
        all_grants_page.click_grant(seeded_e2e_grant["name"])

    grant_details_page = GrantDetailsPage(page, domain, seeded_e2e_grant["name"])
    grant_reports_page = grant_details_page.click_reports(seeded_e2e_grant["name"])
    report_sections_page = grant_reports_page.click_manage_sections(
        grant_name=seeded_e2e_grant["name"], report_name=report_with_groups["name"]
    )
    tasklist_page = report_sections_page.click_preview_report()

    # Check the tasklist has loaded
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_disabled()
    expect(tasklist_page.page.get_by_role("link", name=report_with_groups["sections"][0]["name"])).to_be_visible()

    # Complete the first task with question groups
    complete_task(
        tasklist_page,
        report_with_groups["sections"][0]["name"],
        seeded_e2e_grant["name"],
        report_with_groups["sections"][0]["components"],
    )

    # Check your answers page
    task_check_your_answers(
        tasklist_page,
        seeded_e2e_grant["name"],
        report_with_groups["name"],
        report_with_groups["sections"][0]["components"],
    )

    # Submit the report
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()

    tasklist_page.click_submit_for_preview()


def test_deliver_test_grant_recipient_journey(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:
    """Grant team member triggers test submission via test organisation."""
    assert report_with_groups["id"] is not None, "Setup test must run first"

    # Switch to grant team member
    switch_user(
        page,
        domain,
        e2e_test_secrets,
        DeliverGrantFundingUserType.GRANT_TEAM_MEMBER,
        TEST_DATA_TO_BE_SEEDED["grant_team_email"],
    )

    test_journey_page = DeliverTestGrantRecipientJourneyPage(
        page, domain, seeded_e2e_grant["id"], report_with_groups["id"], report_with_groups["name"]
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(TEST_DATA_TO_BE_SEEDED["test_org_name"])
    test_journey_page.click_start_test_journey()

    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(TEST_DATA_TO_BE_SEEDED["test_org_name"], seeded_e2e_grant["name"])
    access_grant.click_collection(report_with_groups["name"])

    # We should now be on the tasklist page for the submission
    tasklist_page = RunnerTasklistPage(page, domain, seeded_e2e_grant["name"], report_with_groups["name"])

    # Check the tasklist has loaded
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.page.get_by_role("link", name=report_with_groups["sections"][0]["name"])).to_be_visible()

    # Complete the first task with question groups
    complete_task(
        tasklist_page,
        report_with_groups["sections"][0]["name"],
        seeded_e2e_grant["name"],
        report_with_groups["sections"][0]["components"],
    )

    # Check your answers page
    task_check_your_answers(
        tasklist_page,
        seeded_e2e_grant["name"],
        report_with_groups["name"],
        report_with_groups["sections"][0]["components"],
    )

    # Submit the report
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()

    confirmation_page = tasklist_page.click_submit_for_certify()
    confirmation_page.click_return_to_reports()

    # Certify the report
    report_list_page = AccessGrantPage(page, domain)
    report_list_page.click_collection(report_with_groups["name"])

    locked_report_page = ViewLockedReportPage(page, domain, seeded_e2e_grant["name"], report_with_groups["name"])
    expect(locked_report_page.heading).to_be_visible()

    confirm_sign_off_page = locked_report_page.click_sign_off_and_submit()
    sign_off_confirmation_page = confirm_sign_off_page.click_sign_off_and_submit()
    expect(
        page.get_by_text(
            f"Your {report_with_groups['name']} report for {seeded_e2e_grant['name']} has been submitted to the"
        )
    ).to_be_visible()
    sign_off_confirmation_page.click_return_to_reports()

    # Reopen the submission
    grant_reports_page = GrantReportsPage(page, domain, seeded_e2e_grant["name"])
    grant_reports_page.navigate(seeded_e2e_grant["id"])
    submissions_list_page = grant_reports_page.click_view_submissions(report_with_groups["name"])
    view_submission_page = submissions_list_page.click_on_submission(TEST_DATA_TO_BE_SEEDED["test_org_name"])
    reopen_page = view_submission_page.click_reopen_submission()
    reopen_page.fill_reopen_reason("Reopening for e2e tests")
    view_submission_page = reopen_page.click_reopen_submission()
    expect(page.get_by_text("Submission reopened and email sent to")).to_be_visible()

    view_submission_page.click_reset_submission()


def test_zzz_cleanup_grant(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:
    """Cleanup: delete the grant via admin panel. Named zzz_ to run last alphabetically."""
    if not report_with_groups["id"]:
        pytest.skip("No setup data to clean up")

    # Switch to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    # TODO just delete the reports inside seeded_e2e_grant that have been created in this test run
    # Tidy up by deleting the grant via admin panel, which will cascade to all related entities
    delete_grant_recipient_through_admin(
        page, domain, seeded_e2e_grant["name"], expected_grant_recipients_matching_search=2
    )
    delete_grant_through_admin(page, domain, seeded_e2e_grant["name"])
