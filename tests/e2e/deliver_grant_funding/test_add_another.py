import re
import uuid

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import GroupDisplayOptions, QuestionDataType
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser, QuestionDict, QuestionGroupDict, QuestionResponse
from tests.e2e.deliver_grant_funding.helpers import (
    create_grant,
    extract_uuid_from_url,
    navigate_to_report_sections_page,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import create_question_or_group
from tests.e2e.helpers import delete_grant_through_admin

_shared_setup_data: dict | None = None

section_name = "Add another test section"

add_another_one_per_page_group: QuestionGroupDict = {
    "type": "group",
    "text": "Recipient",
    "display_options": GroupDisplayOptions.ONE_QUESTION_PER_PAGE,
    "add_another": True,
    "questions": [
        QuestionDict(
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "What's your first name?",
                "display_text": "First name",
                "answers": [QuestionResponse("Alice"), QuestionResponse("Bob")],
            }
        ),
        QuestionDict(
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "What's your last name?",
                "display_text": "Last name",
                "answers": [QuestionResponse("Smith"), QuestionResponse("Jones")],
            }
        ),
    ],
}


def test_add_another_setup(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """creates a grant/report with one section containing a single add-another group (one question per page)."""
    global _shared_setup_data

    grant_name_uuid = str(uuid.uuid4())
    grant_name = f"E2E add-another grant {grant_name_uuid}"
    report_name = f"E2E add-another report {uuid.uuid4()}"

    # Grant
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = create_grant(grant_name, grant_name_uuid, all_grants_page)
    grant_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")

    # Report
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    add_report_page = grant_reports_page.click_add_report()
    add_report_page.fill_in_report_name(report_name)
    grant_reports_page = add_report_page.click_submit(grant_name)
    grant_reports_page.check_report_exists(report_name)

    # Section
    add_section_page = grant_reports_page.click_add_section(report_name=report_name, grant_name=grant_name)
    collection_id = extract_uuid_from_url(page.url, r"/report/(?P<uuid>[a-f0-9-]+)")
    add_section_page.fill_in_section_name(section_name)
    report_sections_page = add_section_page.click_add_section()
    report_sections_page.check_section_exists(section_name)

    # Add another group
    manage_section_page = report_sections_page.click_manage_section(section_name)
    create_question_or_group(add_another_one_per_page_group, manage_section_page)

    _shared_setup_data = {
        "grant_name": grant_name,
        "grant_name_uuid": grant_name_uuid,
        "grant_id": grant_id,
        "report_name": report_name,
        "collection_id": collection_id,
    }


def fill_entry(
    page: Page,
    domain: str,
    grant_name: str,
    group: QuestionGroupDict,
    answer_index: int,
) -> None:
    """Fill one add-another entry using the answer at answer_index, handling nested groups."""
    for question in group["questions"]:
        if question["type"] == "group":
            fill_entry(page, domain, grant_name, question, answer_index)
        else:
            question_page = RunnerQuestionPage(
                page,
                domain,
                grant_name,
                question["display_text"],
                is_in_a_same_page_group=group["display_options"] == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
            )
            question_page.respond_to_question(
                question_type=question["type"],
                question_text=question["display_text"],
                answer=question["answers"][answer_index].answer,
            )
        if group["display_options"] == GroupDisplayOptions.ONE_QUESTION_PER_PAGE:
            question_page.click_continue()

    if group["display_options"] == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE:
        question_page.click_continue()


def test_add_another_preview_and_fill(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Preview the report and fill in two entries via the add-another journey."""
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    # Navigate to sections and click preview
    report_sections_page = navigate_to_report_sections_page(page, domain, data["grant_name"], data["report_name"])
    tasklist_page = report_sections_page.click_preview_report()

    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_disabled()

    # Click the section
    tasklist_page.click_on_section(section_name)
    expect(page.get_by_role("heading", name="Recipient", exact=True)).to_be_visible()
    expect(page.get_by_text("You have not added any Recipient.")).to_be_visible()

    # Add the first answer
    page.get_by_role("button", name="Add the first answer").click()

    # Fill entry 1
    fill_entry(page, domain, data["grant_name"], add_another_one_per_page_group, answer_index=0)

    # Back on summary
    expect(page.get_by_role("heading", name="Recipient", exact=True)).to_be_visible()
    expect(page.get_by_text("You have added 1 Recipient")).to_be_visible()
    page.get_by_role("radio", name="Yes").click()
    page.get_by_role("button", name="Continue").click()

    # Fill entry 2
    fill_entry(page, domain, data["grant_name"], add_another_one_per_page_group, answer_index=1)

    # Back on summary
    expect(page.get_by_role("heading", name="Recipient", exact=True)).to_be_visible()
    expect(page.get_by_text("You have added 2 Recipient")).to_be_visible()
    page.get_by_role("radio", name="No").click()
    page.get_by_role("button", name="Continue").click()

    # Check your answers
    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, data["grant_name"])
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="Alice, Smith", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Bob, Jones", exact=False)).to_be_visible()

    page.get_by_role("link", name="Back").click()
    expect(page.get_by_role("heading", name="Recipient", exact=True)).to_be_visible()

    page.get_by_role("link", name="Change", exact=False).first.click()

    # change first name
    first_name_page = RunnerQuestionPage(page, domain, data["grant_name"], "First name")
    expect(first_name_page.heading).to_be_visible()
    first_name_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "First name", "Alicia")
    first_name_page.click_continue()

    # back to summary
    last_name_page = RunnerQuestionPage(page, domain, data["grant_name"], "Last name")
    expect(last_name_page.heading).to_be_visible()
    last_name_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "Last name", "Smith")
    last_name_page.click_continue()

    # Back on summary — verify the change is reflected in the entry summary span
    expect(page.get_by_role("heading", name="Recipient", exact=True)).to_be_visible()
    expect(page.locator("span").filter(has_text=re.compile(r"^Alicia, Smith"))).to_be_visible()

    page.get_by_role("link", name="Remove", exact=False).last.click()

    # Confirm remove page"
    expect(page.get_by_role("heading", name="Are you sure you want to remove", exact=False)).to_be_visible()
    page.get_by_role("radio", name="Yes").click()
    page.get_by_role("button", name="Continue").click()

    # Back on summary
    expect(page.get_by_role("heading", name="Recipient", exact=True)).to_be_visible()
    expect(page.get_by_text("You have added 1 Recipient")).to_be_visible()
    expect(page.locator("span").filter(has_text=re.compile(r"^Bob, Jones"))).not_to_be_visible()

    # Finish
    page.get_by_role("radio", name="No").click()
    page.get_by_role("button", name="Continue").click()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, data["grant_name"])
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="Alicia, Smith", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Bob, Jones", exact=False)).not_to_be_visible()

    # Mark as complete
    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=data["report_name"])

    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()


def test_zzz_add_another_cleanup(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Cleanup: delete the grant. Named zzz_ so pytest always runs it last."""
    if _shared_setup_data is None:
        pytest.skip("No setup data to clean up")

    delete_grant_through_admin(page, domain, _shared_setup_data["grant_name"])
