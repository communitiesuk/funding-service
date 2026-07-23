import uuid

import pytest
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
    RunnerCheckYourAnswersPage,
    RunnerTasklistPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import (
    answer_questions_and_check_for_expected_errors,
    complete_task,
    create_question_or_group,
    switch_user,
    task_check_your_answers,
)
from tests.e2e.helpers import delete_grant_through_admin

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

section_1_question_updated: QuestionDict = QuestionDict(
    {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "What is your name?",
        "display_text": "What is your name?",
        "answers": [QuestionResponse("Updated Applicant")],
    }
)

section_2_question_updated: QuestionDict = QuestionDict(
    {
        "type": QuestionDataType.YES_NO,
        "text": "Are you happy?",
        "display_text": "Are you happy?",
        "answers": [QuestionResponse("No")],
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

    # Set up organisations and grant recipients
    # Two orgs one for each journey: reject and approve
    reject_org_name = "End-to-End Testing Organisation (Reject)"
    approve_org_name = "End-to-End Testing Organisation (Approve)"
    collection_lifecycle_tasklist_page = AdminCollectionLifecycleTasklistPage(page, domain, grant_id, collection_id)

    collection_lifecycle_tasklist_page.navigate()
    collection_lifecycle_tasklist_page.click_task("Set up organisations")
    tsv_data = (
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"MHCLG-TEST-ORG-REJECT\t{reject_org_name}\tCentral Government\t\t\n"
        f"MHCLG-TEST-ORG-APPROVE\t{approve_org_name}\tCentral Government\t\t\n"
    )
    set_up_orgs_page = SetUpOrganisationsPage(page, domain, grant_id, collection_id)
    set_up_orgs_page.fill_organisations_tsv_data(tsv_data)
    set_up_orgs_page.click_set_up_organisations()

    collection_lifecycle_tasklist_page.click_task("Set up grant recipients")
    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, grant_id, collection_id)
    set_up_grant_recipients_page.select_organisation(reject_org_name)
    set_up_grant_recipients_page.select_organisation(approve_org_name)
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
        "reject_test_org_name": f"{reject_org_name} (test)",
        "approve_test_org_name": f"{approve_org_name} (test)",
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
    test_journey_page.select_test_organisation(data["reject_test_org_name"])
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(data["reject_test_org_name"], data["grant_name"])
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

    # Back on the Deliver side
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, data["grant_name"])
    grant_pre_award_forms_page.navigate(data["grant_id"])
    submissions_list_page = grant_pre_award_forms_page.click_view_submissions(data["collection_name"])
    view_submission_page = submissions_list_page.click_on_submission(data["reject_test_org_name"])

    # Reopen the submission flow
    request_or_allow_changes_page = view_submission_page.click_request_or_allow_changes()
    reopen_page = request_or_allow_changes_page.click_no_just_allow_changes()
    reopen_page.fill_reopen_reason("Please adjust information")
    view_submission_page = reopen_page.click_reopen_submission()
    # Check for success message
    expect(page.get_by_text("Submission reopened and email sent to")).to_be_visible()
    # Check for Submission status
    expect(view_submission_page.status_tag_with_text("In progress")).to_be_visible()

    # Back on the Access side
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(data["reject_test_org_name"], data["grant_name"])
    access_grant.click_collection(data["collection_name"])

    tasklist_page = RunnerTasklistPage(page, domain, data["grant_name"], data["collection_name"])
    expect(tasklist_page.heading).to_be_visible()
    # Both sections and the overall status should now be "In progress"
    expect(tasklist_page.status_tag_with_text("In progress")).to_have_count(3)

    # Resubmit sections
    # Update Section 1
    tasklist_page.click_on_section(section_name=SECTION_1_NAME)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, data["grant_name"])
    question_page = check_your_answers_page.click_change_answer(section_1_question_updated["display_text"])
    answer_questions_and_check_for_expected_errors([section_1_question_updated], question_page, None)
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], [section_1_question_updated])

    # Leave Section 2 as is
    tasklist_page.click_on_section(section_name=SECTION_2_NAME)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, data["grant_name"])
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], [section_2_question])

    # Both sections show "Changes made" and the overall status is "Ready to submit"
    expect(tasklist_page.status_tag_with_text("Changes made")).to_have_count(1)
    expect(tasklist_page.status_tag_with_text("Ready to submit")).to_have_count(1)

    # Resubmit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_resubmit_page = tasklist_page.click_submit_for_direct_submission()
    resubmit_confirmation_page = confirm_resubmit_page.click_confirm_and_submit()
    expect(resubmit_confirmation_page.heading).to_be_visible()

    # Back on the Deliver side
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, data["grant_name"])
    grant_pre_award_forms_page.navigate(data["grant_id"])
    submissions_list_page = grant_pre_award_forms_page.click_view_submissions(data["collection_name"])
    view_submission_page = submissions_list_page.click_on_submission(data["reject_test_org_name"])

    # Check for the Submission status
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    # Check that Changed status shows up
    expect(view_submission_page.status_tag_with_text("Changed")).to_be_visible()
    # Check that "Original response" elements show up
    expect(page.get_by_text("Original response")).to_be_visible()

    # Reject the resubmission
    approve_or_reject_page = view_submission_page.click_approve_or_reject()

    # Check for the Submission messages and status
    view_submission_page = approve_or_reject_page.reject_submission("Information still incorrect")
    expect(page.get_by_role("heading", name="Submission marked as rejected")).to_be_visible()
    expect(view_submission_page.status_tag_with_text("Marked as rejected")).to_be_visible()

    # Back on the Access side: the assessment is internal-only
    # The grant recipient should still just see "Submitted with changes"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(data["reject_test_org_name"], data["grant_name"])
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    expect(page.get_by_text("Marked as rejected")).not_to_be_visible()


def test_request_changes_and_approve(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> None:
    """Grant recipient submits form; grant team requests changes to one section; grant recipient resubmits;
    grant team approves."""
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
    test_journey_page.select_test_organisation(data["approve_test_org_name"])
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(data["approve_test_org_name"], data["grant_name"])
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

    # On the Deliver side: request changes to Section 2 only
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, data["grant_name"])
    grant_pre_award_forms_page.navigate(data["grant_id"])
    submissions_list_page = grant_pre_award_forms_page.click_view_submissions(data["collection_name"])
    view_submission_page = submissions_list_page.click_on_submission(data["approve_test_org_name"])

    request_or_allow_changes_page = view_submission_page.click_request_or_allow_changes()
    request_changes_page = request_or_allow_changes_page.click_yes_request_changes()
    request_changes_page.select_section(SECTION_2_NAME)
    view_submission_page = request_changes_page.request_changes("Please update your answer to this section")
    expect(page.get_by_role("heading", name="Changes have been requested")).to_be_visible()

    # Back on the Access side: only the requested section is "Changes requested"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(data["approve_test_org_name"], data["grant_name"])
    access_grant.click_collection(data["collection_name"])

    tasklist_page = RunnerTasklistPage(page, domain, data["grant_name"], data["collection_name"])
    expect(tasklist_page.heading).to_be_visible()
    expect(tasklist_page.status_tag_with_text("Changes requested")).to_have_count(2)

    # Update the requested section
    tasklist_page.click_on_section(section_name=SECTION_2_NAME)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, data["grant_name"])
    expect(check_your_answers_page.changes_requested_reason_inset).to_contain_text(
        "Please update your answer to this section"
    )
    question_page = check_your_answers_page.click_change_answer(section_2_question_updated["display_text"])
    answer_questions_and_check_for_expected_errors([section_2_question_updated], question_page, None)
    task_check_your_answers(tasklist_page, data["grant_name"], data["collection_name"], [section_2_question_updated])

    # The section is now "Changes made" and the overall status is "Ready to submit"
    expect(tasklist_page.status_tag_with_text("Changes made")).to_have_count(1)
    expect(tasklist_page.status_tag_with_text("Ready to submit")).to_have_count(1)

    # Resubmit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_resubmit_page = tasklist_page.click_submit_for_direct_submission()
    resubmit_confirmation_page = confirm_resubmit_page.click_confirm_and_submit()
    expect(resubmit_confirmation_page.heading).to_be_visible()

    # Back on the Deliver side: approve the resubmission
    grant_pre_award_forms_page.navigate(data["grant_id"])
    submissions_list_page = grant_pre_award_forms_page.click_view_submissions(data["collection_name"])
    view_submission_page = submissions_list_page.click_on_submission(data["approve_test_org_name"])

    approve_or_reject_page = view_submission_page.click_approve_or_reject()
    view_submission_page = approve_or_reject_page.approve_submission()
    expect(page.get_by_role("heading", name="Submission marked as approved")).to_be_visible()
    expect(view_submission_page.status_tag_with_text("Marked as approved")).to_be_visible()

    # Back on the Access side: the assessment is internal-only
    # The grant recipient should still just see "Submitted with changes"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(data["approve_test_org_name"], data["grant_name"])
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    expect(page.get_by_text("Marked as approved")).not_to_be_visible()


def test_zzz_pre_award_validation_cleanup(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> None:
    """Cleanup: delete the grant. Named zzz_ to run last alphabetically."""
    if _shared_setup_data is None:
        pytest.skip("No setup data to clean up")

    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)
    delete_grant_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
