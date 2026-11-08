import uuid
from typing import Callable

from playwright.sync_api import Page, expect

from app.common.data.types import CollectionType, GrantRecipientStatusEnum, QuestionDataType
from tests.e2e.access_grant_funding.pages import AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import DeliverGrantFundingUserType, e2e_user_configs, switch_user
from tests.e2e.dataclasses import (
    BuiltGrantScenario,
    CollectionConfig,
    GrantScenario,
    OrganisationConfig,
    QuestionDict,
    QuestionResponse,
    SectionDict,
)
from tests.e2e.deliver_grant_funding.helpers import (
    answer_questions_and_check_for_expected_errors,
    complete_task,
    task_check_your_answers,
)
from tests.e2e.deliver_grant_funding.reports_pages import (
    GrantPreAwardFormsPage,
    PreAwardTestGrantRecipientJourneyPage,
    RunnerCheckYourAnswersPage,
    RunnerTasklistPage,
)

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


def test_pre_award_validation(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    build_grant_scenario: Callable[..., BuiltGrantScenario],
) -> None:
    """Build one grant/collection with two grant recipients, then run two pre-award validation journeys against
    it: reopen-then-reject a submission, and request-changes-then-approve a resubmission."""
    collection_name = f"E2E pre-award validation {uuid.uuid4()}"
    reject_org_name = f"End-to-End Testing Organisation (Reject) {uuid.uuid4()}"
    approve_org_name = f"End-to-End Testing Organisation (Approve) {uuid.uuid4()}"
    reject_test_org_name = f"{reject_org_name} (test)"
    approve_test_org_name = f"{approve_org_name} (test)"
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email

    handle = build_grant_scenario(
        GrantScenario(
            add_grant_team_member=True,
            collection=CollectionConfig(
                name=collection_name,
                type=CollectionType.APPLICATION,
                sections=[
                    SectionDict(name=SECTION_1_NAME, components=[section_1_question]),
                    SectionDict(name=SECTION_2_NAME, components=[section_2_question]),
                ],
                allow_validation=True,
                turn_off_requires_certification=True,
                set_live=True,
            ),
            organisations=[
                OrganisationConfig(
                    name=reject_org_name,
                    external_id=f"MHCLG-TEST-ORG-{uuid.uuid4()}",
                    grant_recipient_status=GrantRecipientStatusEnum.ALLOCATED,
                    set_certifiers=False,
                ),
                OrganisationConfig(
                    name=approve_org_name,
                    external_id=f"MHCLG-TEST-ORG-{uuid.uuid4()}",
                    grant_recipient_status=GrantRecipientStatusEnum.ALLOCATED,
                    set_certifiers=False,
                ),
            ],
        )
    )

    # Switch to grant team member to trigger the test recipient journeys
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)

    # --- Scenario 1: reopen then reject -------------------------------------------------------

    test_journey_page = PreAwardTestGrantRecipientJourneyPage(
        page, domain, handle.grant_id, handle.collection_id, collection_name
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(reject_test_org_name)
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(reject_test_org_name, handle.grant_name)
    access_grant.click_collection(collection_name)

    # Now on the submission tasklist
    tasklist_page = RunnerTasklistPage(page, domain, handle.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()

    # Complete both sections
    complete_task(tasklist_page, SECTION_1_NAME, handle.grant_name, [section_1_question])
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_1_question])

    complete_task(tasklist_page, SECTION_2_NAME, handle.grant_name, [section_2_question])
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_2_question])

    # Submit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
    confirmation_page = confirm_submit_page.click_confirm_and_submit()
    expect(confirmation_page.heading).to_be_visible()

    # Back on the Deliver side
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, handle.grant_name)
    grant_pre_award_forms_page.navigate(handle.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(collection_name, "submitted")
    view_submission_page = submissions_list_page.click_on_submission(reject_test_org_name)

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
    access_grant = access_home.select_grant(reject_test_org_name, handle.grant_name)
    access_grant.click_collection(collection_name)

    tasklist_page = RunnerTasklistPage(page, domain, handle.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()
    # Both sections and the overall status should now be "In progress"
    expect(tasklist_page.status_tag_with_text("In progress")).to_have_count(3)

    # Resubmit sections
    # Update Section 1
    tasklist_page.click_on_section(section_name=SECTION_1_NAME)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    question_page = check_your_answers_page.click_change_answer(section_1_question_updated["display_text"])
    answer_questions_and_check_for_expected_errors([section_1_question_updated], question_page, None)
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_1_question_updated])

    # Leave Section 2 as is
    tasklist_page.click_on_section(section_name=SECTION_2_NAME)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_2_question])

    # Both sections show "Changes made" and the overall status is "Ready to submit"
    expect(tasklist_page.status_tag_with_text("Changes made")).to_have_count(1)
    expect(tasklist_page.status_tag_with_text("Ready to submit")).to_have_count(1)

    # Resubmit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_resubmit_page = tasklist_page.click_submit_for_direct_submission()
    resubmit_confirmation_page = confirm_resubmit_page.click_confirm_and_submit()
    expect(resubmit_confirmation_page.heading).to_be_visible()

    # Back on the Deliver side
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, handle.grant_name)
    grant_pre_award_forms_page.navigate(handle.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(
        collection_name, submission_status="submitted"
    )
    view_submission_page = submissions_list_page.click_on_submission(reject_test_org_name)

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
    access_grant = access_home.select_grant(reject_test_org_name, handle.grant_name)
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    expect(page.get_by_text("Marked as rejected")).not_to_be_visible()

    # --- Scenario 2: request changes then approve ---------------------------------------------

    test_journey_page = PreAwardTestGrantRecipientJourneyPage(
        page, domain, handle.grant_id, handle.collection_id, collection_name
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(approve_test_org_name)
    test_journey_page.click_start_test_journey()

    # Navigate to the access side as the grant recipient
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(approve_test_org_name, handle.grant_name)
    access_grant.click_collection(collection_name)

    # Now on the submission tasklist
    tasklist_page = RunnerTasklistPage(page, domain, handle.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()

    # Complete both sections
    complete_task(tasklist_page, SECTION_1_NAME, handle.grant_name, [section_1_question])
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_1_question])

    complete_task(tasklist_page, SECTION_2_NAME, handle.grant_name, [section_2_question])
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_2_question])

    # Submit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
    confirmation_page = confirm_submit_page.click_confirm_and_submit()
    expect(confirmation_page.heading).to_be_visible()

    # On the Deliver side: request changes to Section 2 only
    grant_pre_award_forms_page = GrantPreAwardFormsPage(page, domain, handle.grant_name)
    grant_pre_award_forms_page.navigate(handle.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(
        collection_name, submission_status="submitted"
    )
    view_submission_page = submissions_list_page.click_on_submission(approve_test_org_name)

    request_or_allow_changes_page = view_submission_page.click_request_or_allow_changes()
    request_changes_page = request_or_allow_changes_page.click_yes_request_changes()
    request_changes_page.select_section(SECTION_2_NAME)
    view_submission_page = request_changes_page.request_changes("Please update your answer to this section")
    expect(page.get_by_role("heading", name="Changes have been requested")).to_be_visible()

    # Back on the Access side: only the requested section is "Changes requested"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(approve_test_org_name, handle.grant_name)
    access_grant.click_collection(collection_name)

    tasklist_page = RunnerTasklistPage(page, domain, handle.grant_name, collection_name)
    expect(tasklist_page.heading).to_be_visible()
    expect(tasklist_page.status_tag_with_text("Changes requested")).to_have_count(2)

    # Update the requested section
    tasklist_page.click_on_section(section_name=SECTION_2_NAME)
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.changes_requested_reason_inset).to_contain_text(
        "Please update your answer to this section"
    )
    question_page = check_your_answers_page.click_change_answer(section_2_question_updated["display_text"])
    answer_questions_and_check_for_expected_errors([section_2_question_updated], question_page, None)
    task_check_your_answers(tasklist_page, handle.grant_name, collection_name, [section_2_question_updated])

    # The section is now "Changes made" and the overall status is "Ready to submit"
    expect(tasklist_page.status_tag_with_text("Changes made")).to_have_count(1)
    expect(tasklist_page.status_tag_with_text("Ready to submit")).to_have_count(1)

    # Resubmit the form
    expect(tasklist_page.submit_button).to_be_enabled()
    confirm_resubmit_page = tasklist_page.click_submit_for_direct_submission()
    resubmit_confirmation_page = confirm_resubmit_page.click_confirm_and_submit()
    expect(resubmit_confirmation_page.heading).to_be_visible()

    # Back on the Deliver side: approve the resubmission
    grant_pre_award_forms_page.navigate(handle.grant_id)
    submissions_list_page = grant_pre_award_forms_page.click_view_test_submissions(
        collection_name, submission_status="submitted"
    )
    view_submission_page = submissions_list_page.click_on_submission(approve_test_org_name)

    approve_or_reject_page = view_submission_page.click_approve_or_reject()
    view_submission_page = approve_or_reject_page.approve_submission()
    expect(page.get_by_role("heading", name="Submission marked as approved")).to_be_visible()
    expect(view_submission_page.status_tag_with_text("Marked as approved")).to_be_visible()

    # Back on the Access side: the assessment is internal-only
    # The grant recipient should still just see "Submitted with changes"
    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_grant = access_home.select_grant(approve_test_org_name, handle.grant_name)
    expect(page.get_by_text("Submitted with changes")).to_be_visible()
    expect(page.get_by_text("Marked as approved")).not_to_be_visible()
