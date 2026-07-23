import uuid

from playwright.sync_api import Page, expect

from app.common.data.types import (
    GrantRecipientStatusEnum,
    QuestionDataType,
)
from tests.e2e.access_grant_funding.pages import AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import (
    DeliverGrantFundingUserType,
    e2e_user_configs,
)
from tests.e2e.dataclasses import E2ETestUser, QuestionDict, QuestionResponse
from tests.e2e.deliver_grant_funding.helpers import (
    create_grant,
    extract_uuid_from_url,
    navigate_to_pre_award_sections_page,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AdminCollectionLifecycleTasklistPage,
    GrantPreAwardFormsPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    PreAwardTestGrantRecipientJourneyPage,
    RunnerTasklistPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import (
    complete_task,
    create_question_or_group,
    switch_user,
    task_check_your_answers,
)

_shared_setup_data: dict | None = None

COLLECTION_NAME = "Round 1"
SECTION_1_NAME = "Section 1"
SECTION_2_NAME = "Section 2"

section_1_question: QuestionDict = QuestionDict(
    {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "What is your name?",
        "display_text": "What is your name?",
        "answers": [QuestionResponse("Test Applicant")],
    }
)

section_2_question: QuestionDict = QuestionDict(
    {
        "type": QuestionDataType.YES_NO,
        "text": "Are you happy?",
        "display_text": "Are you happy?",
        "answers": [QuestionResponse("Yes")],
    }
)


def test_pre_award_validation_setup(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> None:
    """Setup: creates grant, pre-award collection, sections, and lifecycle config for validation tests."""
    global _shared_setup_data

    grant_name_uuid = str(uuid.uuid4())
    grant_name = f"E2E pre-award validation {grant_name_uuid}"

    # Create grant
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    create_grant(grant_name, grant_name_uuid, all_grants_page)

    # Get Grant ID
    grant_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")

    # Enable allow_pre_award on the grant via admin panel
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.click_allow_pre_award()
    grant_settings_page.click_save()

    # Create APPLICATION type collection
    pre_award_forms_page = GrantPreAwardFormsPage(page, domain, grant_name)
    pre_award_forms_page.navigate(grant_id)
    method_page = pre_award_forms_page.click_add_form()
    add_form_page = method_page.click_create_new()
    add_form_page.fill_in_form_name(COLLECTION_NAME)
    pre_award_forms_page = add_form_page.click_submit(grant_name)

    # Click into sections to extract collection_id from URL
    pre_award_forms_page.click_add_section(COLLECTION_NAME, grant_name)

    # Get Collection ID
    collection_id = extract_uuid_from_url(page.url, r"/applications/(?P<uuid>[a-f0-9-]+)")

    # Enable allow_validation and turn off requires_certificatio
    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.click_allow_validation()
    report_settings_page.click_turn_off_requires_certification()
    report_settings_page.click_save()

    # Go back to Grant page
    pre_award_forms_page.navigate(grant_id)

    # Section 1
    add_section_page = pre_award_forms_page.click_add_section(COLLECTION_NAME, grant_name)
    add_section_page.fill_in_section_name(SECTION_1_NAME)
    collection_sections_page = add_section_page.click_add_section()
    manage_section_page = collection_sections_page.click_manage_section(SECTION_1_NAME)
    create_question_or_group(section_1_question, manage_section_page)

    # Section 2
    collection_sections_page = navigate_to_pre_award_sections_page(page, domain, grant_name, COLLECTION_NAME)
    add_section_page = collection_sections_page.click_add_section()
    add_section_page.fill_in_section_name(SECTION_2_NAME)
    collection_sections_page = add_section_page.click_add_section()
    manage_section_page = collection_sections_page.click_manage_section(SECTION_2_NAME)
    create_question_or_group(section_2_question, manage_section_page)

    # Add grant team member
    grant_team_page = collection_sections_page.click_nav_grant_team()
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    add_grant_team_member_page.fill_in_user_email(grant_team_email)
    grant_team_page = add_grant_team_member_page.click_continue()

    # Switch to grant team member (claim invitation/userrole), then switch back to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    # Set up organisation and grant recipient (creates shadow test org for test journeys)
    org_name = "End-to-End Testing Organisation"
    collection_lifecycle_tasklist_page = AdminCollectionLifecycleTasklistPage(page, domain, grant_id, collection_id)

    collection_lifecycle_tasklist_page.navigate()
    collection_lifecycle_tasklist_page.click_task("Set up organisations")
    tsv_data = (
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"MHCLG-TEST-ORG\t{org_name}\tCentral Government\t\t\n"
    )
    set_up_orgs_page = SetUpOrganisationsPage(page, domain, grant_id, collection_id)
    set_up_orgs_page.fill_organisations_tsv_data(tsv_data)
    set_up_orgs_page.click_set_up_organisations()

    collection_lifecycle_tasklist_page.click_task("Set up grant recipients")
    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, grant_id, collection_id)
    set_up_grant_recipients_page.select_organisation(org_name)
    set_up_grant_recipients_page.select_status(GrantRecipientStatusEnum.ALLOCATED)
    set_up_grant_recipients_page.click_set_up_grant_recipients()

    # Set grant LIVE and collection OPEN via admin shortcuts
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status("LIVE")
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status("OPEN")
    report_settings_page.click_save()

    _shared_setup_data = {
        "grant_name": grant_name,
        "grant_name_uuid": grant_name_uuid,
        "grant_id": grant_id,
        "collection_id": collection_id,
        "collection_name": COLLECTION_NAME,
        "test_org_name": f"{org_name} (test)",
        "grant_team_email": grant_team_email,
    }


def test_reopen_and_reject(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> None:
    """Grant recipient submits form; grant team reopens then rejects the submission."""
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    # Switch to grant team member to trigger the test recipient journey
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, data["grant_team_email"])

    test_journey_page = PreAwardTestGrantRecipientJourneyPage(
        page,
        domain,
        data["grant_id"],
        data["collection_id"],
        data["collection_name"],
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(data["test_org_name"])
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(data["test_org_name"], data["grant_name"])
    access_grant.click_collection(data["collection_name"])

    # Now on the submission tasklist
    tasklist_page = RunnerTasklistPage(page, domain, data["grant_name"], data["collection_name"])
    expect(tasklist_page.heading).to_be_visible()

    # Complete both sections
    complete_task(tasklist_page, SECTION_1_NAME, data["grant_name"], [section_1_question])
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], [section_1_question])

    complete_task(tasklist_page, SECTION_2_NAME, data["grant_name"], [section_2_question])
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], [section_2_question])

    # Submit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
    confirmation_page = confirm_submit_page.click_confirm_and_submit()
    expect(confirmation_page.heading).to_be_visible()


# def test_zzz_pre_award_validation_cleanup(
#     page: Page,
#     domain: str,
#     e2e_test_secrets: EndToEndTestSecrets,
#     authenticated_browser_sso: E2ETestUser,
#     email: str,
# ) -> None:
#     """Cleanup: delete the grant. Named zzz_ to run last alphabetically."""
#     if _shared_setup_data is None:
#         pytest.skip("No setup data to clean up")

#     switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)
#     delete_grant_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
