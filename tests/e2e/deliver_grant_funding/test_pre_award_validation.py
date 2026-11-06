import uuid
from typing import Callable

from playwright.sync_api import Page, expect

from app.common.data.types import GrantRecipientStatusEnum, QuestionDataType
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import DeliverGrantFundingUserType, e2e_user_configs, switch_user
from tests.e2e.dataclasses import GrantScenario, GrantScenarioHandle, QuestionDict, QuestionResponse, SectionDict
from tests.e2e.pages.access_pages import AccessHomePage
from tests.e2e.pages.deliver_pages import GrantPreAwardFormsPage, PreAwardTestGrantRecipientJourneyPage
from tests.e2e.pages.misc_pages import RunnerCheckYourAnswersPage, RunnerTasklistPage
from tests.e2e.question_helpers import (
    answer_questions_and_check_for_expected_errors,
    complete_task,
    task_check_your_answers,
)


def test_reopen_and_reject(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    email: str,
    build_grant_scenario: Callable[..., GrantScenarioHandle],
) -> None:
    """Grant recipient submits form; grant team reopens then rejects the submission."""
    section_1_name = "Section 1"
    section_2_name = "Section 2"
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

    collection_name = "Round 1"
    org_name = f"End-to-End Testing Organisation (Reject) {uuid.uuid4()}"
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    scenario = build_grant_scenario(
        GrantScenario(
            collection_name=collection_name,
            collection_type="application",
            sections=[
                SectionDict(name=section_1_name, components=[section_1_question]),
                SectionDict(name=section_2_name, components=[section_2_question]),
            ],
            allow_validation=True,
            turn_off_requires_certification=True,
            grant_team_member_email=grant_team_email,
            org_name=org_name,
            org_external_id=f"MHCLG-TEST-ORG-{uuid.uuid4().hex[:8].upper()}",
            recipient_status=GrantRecipientStatusEnum.ALLOCATED,
            set_live=True,
        )
    )
    test_org_name = f"{org_name} (test)"

    # Switch to grant team member to trigger the test recipient journey
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)

    test_journey_page = PreAwardTestGrantRecipientJourneyPage(
        page, domain, scenario.grant_id, scenario.collection_id, collection_name
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(test_org_name)
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(test_org_name, scenario.grant_name)
    access_grant.click_collection(collection_name)

    # Now on the submission tasklist
    tasklist_page = RunnerTasklistPage(page, domain, scenario.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()

    # Complete both sections
    complete_task(tasklist_page, section_1_name, scenario.grant_name, [section_1_question])
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_1_question])

    complete_task(tasklist_page, section_2_name, scenario.grant_name, [section_2_question])
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_2_question])

    # Submit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
    confirmation_page = confirm_submit_page.click_confirm_and_submit()
    expect(confirmation_page.heading).to_be_visible()

    # Back on the Deliver side
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, scenario.grant_name)
    grant_pre_award_forms_page.navigate(scenario.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(collection_name, "submitted")
    view_submission_page = submissions_list_page.click_on_submission(test_org_name)

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
    access_grant = access_home.select_grant(test_org_name, scenario.grant_name)
    access_grant.click_collection(collection_name)

    tasklist_page = RunnerTasklistPage(page, domain, scenario.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()
    # Both sections and the overall status should now be "In progress"
    expect(tasklist_page.status_tag_with_text("In progress")).to_have_count(3)

    # Resubmit sections
    # Update Section 1
    tasklist_page.click_on_section(section_name=section_1_name)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, scenario.grant_name)
    question_page = check_your_answers_page.click_change_answer(section_1_question_updated["display_text"])
    answer_questions_and_check_for_expected_errors([section_1_question_updated], question_page, None)
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_1_question_updated])

    # Leave Section 2 as is
    tasklist_page.click_on_section(section_name=section_2_name)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, scenario.grant_name)
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_2_question])

    # Both sections show "Changes made" and the overall status is "Ready to submit"
    expect(tasklist_page.status_tag_with_text("Changes made")).to_have_count(1)
    expect(tasklist_page.status_tag_with_text("Ready to submit")).to_have_count(1)

    # Resubmit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_resubmit_page = tasklist_page.click_submit_for_direct_submission()
    resubmit_confirmation_page = confirm_resubmit_page.click_confirm_and_submit()
    expect(resubmit_confirmation_page.heading).to_be_visible()

    # Back on the Deliver side
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, scenario.grant_name)
    grant_pre_award_forms_page.navigate(scenario.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(
        collection_name, submission_status="submitted"
    )
    view_submission_page = submissions_list_page.click_on_submission(test_org_name)

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
    access_grant = access_home.select_grant(test_org_name, scenario.grant_name)
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    expect(page.get_by_text("Marked as rejected")).not_to_be_visible()


def test_request_changes_and_approve(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    email: str,
    build_grant_scenario: Callable[..., GrantScenarioHandle],
) -> None:
    """Grant recipient submits form; grant team requests changes to one section; grant recipient resubmits;
    grant team approves."""
    section_1_name = "Section 1"
    section_2_name = "Section 2"
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
    section_2_question_updated: QuestionDict = QuestionDict(
        {
            "type": QuestionDataType.YES_NO,
            "text": "Are you happy?",
            "display_text": "Are you happy?",
            "answers": [QuestionResponse("No")],
        }
    )

    collection_name = "Round 1"
    org_name = f"End-to-End Testing Organisation (Approve) {uuid.uuid4()}"
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    scenario = build_grant_scenario(
        GrantScenario(
            collection_name=collection_name,
            collection_type="application",
            sections=[
                SectionDict(name=section_1_name, components=[section_1_question]),
                SectionDict(name=section_2_name, components=[section_2_question]),
            ],
            allow_validation=True,
            turn_off_requires_certification=True,
            grant_team_member_email=grant_team_email,
            org_name=org_name,
            org_external_id=f"MHCLG-TEST-ORG-{uuid.uuid4().hex[:8].upper()}",
            recipient_status=GrantRecipientStatusEnum.ALLOCATED,
            set_live=True,
        )
    )
    test_org_name = f"{org_name} (test)"

    # Switch to grant team member to trigger the test recipient journey
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)

    test_journey_page = PreAwardTestGrantRecipientJourneyPage(
        page, domain, scenario.grant_id, scenario.collection_id, collection_name
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(test_org_name)
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(test_org_name, scenario.grant_name)
    access_grant.click_collection(collection_name)

    # Now on the submission tasklist
    tasklist_page = RunnerTasklistPage(page, domain, scenario.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()

    # Complete both sections
    complete_task(tasklist_page, section_1_name, scenario.grant_name, [section_1_question])
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_1_question])

    complete_task(tasklist_page, section_2_name, scenario.grant_name, [section_2_question])
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_2_question])

    # Submit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
    confirmation_page = confirm_submit_page.click_confirm_and_submit()
    expect(confirmation_page.heading).to_be_visible()

    # On the Deliver side: request changes to Section 2 only
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, scenario.grant_name)
    grant_pre_award_forms_page.navigate(scenario.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(
        collection_name, submission_status="submitted"
    )
    view_submission_page = submissions_list_page.click_on_submission(test_org_name)

    request_or_allow_changes_page = view_submission_page.click_request_or_allow_changes()
    request_changes_page = request_or_allow_changes_page.click_yes_request_changes()
    request_changes_page.select_section(section_2_name)
    view_submission_page = request_changes_page.request_changes("Please update your answer to this section")
    expect(page.get_by_role("heading", name="Changes have been requested")).to_be_visible()

    # Back on the Access side: only the requested section is "Changes requested"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(test_org_name, scenario.grant_name)
    access_grant.click_collection(collection_name)

    tasklist_page = RunnerTasklistPage(page, domain, scenario.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()
    expect(tasklist_page.status_tag_with_text("Changes requested")).to_have_count(2)

    # Update the requested section
    tasklist_page.click_on_section(section_name=section_2_name)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, scenario.grant_name)
    expect(check_your_answers_page.changes_requested_reason_inset).to_contain_text(
        "Please update your answer to this section"
    )
    question_page = check_your_answers_page.click_change_answer(section_2_question_updated["display_text"])
    answer_questions_and_check_for_expected_errors([section_2_question_updated], question_page, None)
    task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [section_2_question_updated])

    # The section is now "Changes made" and the overall status is "Ready to submit"
    expect(tasklist_page.status_tag_with_text("Changes made")).to_have_count(1)
    expect(tasklist_page.status_tag_with_text("Ready to submit")).to_have_count(1)

    # Resubmit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_resubmit_page = tasklist_page.click_submit_for_direct_submission()
    resubmit_confirmation_page = confirm_resubmit_page.click_confirm_and_submit()
    expect(resubmit_confirmation_page.heading).to_be_visible()

    # Back on the Deliver side: approve the resubmission
    grant_pre_award_forms_page.navigate(scenario.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(
        collection_name, submission_status="submitted"
    )
    view_submission_page = submissions_list_page.click_on_submission(test_org_name)

    approve_or_reject_page = view_submission_page.click_approve_or_reject()
    view_submission_page = approve_or_reject_page.approve_submission()
    expect(page.get_by_role("heading", name="Submission marked as approved")).to_be_visible()
    expect(view_submission_page.status_tag_with_text("Marked as approved")).to_be_visible()

    # Back on the Access side: the assessment is internal-only
    # The grant recipient should still just see "Submitted with changes"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(test_org_name, scenario.grant_name)
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    expect(page.get_by_text("Marked as approved")).not_to_be_visible()
