import re
import uuid
from typing import Callable

from playwright.sync_api import Page, expect

from app.common.data.types import GroupDisplayOptions, QuestionDataType
from tests.e2e.dataclasses import (
    BuiltGrantScenario,
    CollectionConfig,
    GrantScenario,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    SectionDict,
)
from tests.e2e.deliver_grant_funding.helpers import navigate_to_report_sections_page
from tests.e2e.deliver_grant_funding.reports_pages import (
    RunnerAddAnotherRemovePage,
    RunnerAddAnotherSummaryPage,
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
)

recipient_section_name = "Add another one per page section"
address_section_name = "Add another same page section"
organisation_section_name = "Add another nested group section"

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

add_another_all_on_same_page_group: QuestionGroupDict = {
    "type": "group",
    "text": "Address",
    "display_options": GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
    "add_another": True,
    "questions": [
        QuestionDict(
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "What is your street?",
                "display_text": "Street",
                "answers": [QuestionResponse("123 Fake Street"), QuestionResponse("456 Real Road")],
            }
        ),
        QuestionDict(
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "What is your city?",
                "display_text": "City",
                "answers": [QuestionResponse("London"), QuestionResponse("Manchester")],
            }
        ),
    ],
}

add_another_nested_group: QuestionGroupDict = {
    "type": "group",
    "text": "Organisation",
    "display_options": GroupDisplayOptions.ONE_QUESTION_PER_PAGE,
    "add_another": True,
    "questions": [
        QuestionDict(
            {
                "type": QuestionDataType.TEXT_SINGLE_LINE,
                "text": "What is the organisation name?",
                "display_text": "Organisation name",
                "answers": [QuestionResponse("Acme Corp"), QuestionResponse("Globex")],
            }
        ),
        {
            "type": "group",
            "text": "Contact details",
            "display_options": GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
            "questions": [
                QuestionDict(
                    {
                        "type": QuestionDataType.TEXT_SINGLE_LINE,
                        "text": "What is the contact name?",
                        "display_text": "Contact name",
                        "answers": [QuestionResponse("Alice Smith"), QuestionResponse("Bob Jones")],
                    }
                ),
                QuestionDict(
                    {
                        "type": QuestionDataType.EMAIL,
                        "text": "What is the contact email?",
                        "display_text": "Contact email",
                        "answers": [QuestionResponse("alice@example.com"), QuestionResponse("bob@example.com")],
                    }
                ),
            ],
        },
    ],
}


def fill_entry(
    page: Page,
    domain: str,
    grant_name: str,
    group: QuestionGroupDict,
    answer_index: int,
) -> None:
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
    page: Page,
    domain: str,
    build_grant_scenario: Callable[..., BuiltGrantScenario],
) -> None:
    """Build a report with one section per "add another" scenario (one-question-per-page group, all-on-one-page
    group, and a nested group), then preview and fill each: add two entries, change and remove one, and check the
    final answers before marking each section complete."""
    report_name = f"E2E add-another report {uuid.uuid4()}"

    handle = build_grant_scenario(
        GrantScenario(
            collection=CollectionConfig(
                name=report_name,
                sections=[
                    SectionDict(name=recipient_section_name, components=[add_another_one_per_page_group]),
                    SectionDict(name=address_section_name, components=[add_another_all_on_same_page_group]),
                    SectionDict(name=organisation_section_name, components=[add_another_nested_group]),
                ],
            ),
        )
    )

    report_sections_page = navigate_to_report_sections_page(page, domain, handle.grant_name, report_name)
    tasklist_page = report_sections_page.click_preview_report()

    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_disabled()

    # Scenario 1
    tasklist_page.click_on_section(recipient_section_name)
    recipient_summary = RunnerAddAnotherSummaryPage(page, domain, handle.grant_name, "Recipient")
    recipient_summary.expect_empty()
    recipient_summary.click_add_first_answer()

    fill_entry(page, domain, handle.grant_name, add_another_one_per_page_group, answer_index=0)

    recipient_summary.expect_count(1)
    recipient_summary.click_add_another_yes()

    fill_entry(page, domain, handle.grant_name, add_another_one_per_page_group, answer_index=1)

    recipient_summary.expect_count(2)
    recipient_summary.click_add_another_no()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="Alice, Smith", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Bob, Jones", exact=False)).to_be_visible()

    page.get_by_role("link", name="Back").click()
    recipient_summary.click_change(index=0)

    first_name_page = RunnerQuestionPage(page, domain, handle.grant_name, "First name")
    expect(first_name_page.heading).to_be_visible()
    first_name_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "First name", "Alicia")
    first_name_page.click_continue()

    last_name_page = RunnerQuestionPage(page, domain, handle.grant_name, "Last name")
    expect(last_name_page.heading).to_be_visible()
    last_name_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "Last name", "Smith")
    last_name_page.click_continue()

    expect(page.locator("span").filter(has_text=re.compile(r"^Alicia, Smith"))).to_be_visible()
    recipient_summary.click_remove_last()

    remove_page = RunnerAddAnotherRemovePage(page, domain, handle.grant_name)
    remove_page.confirm_remove()

    recipient_summary.expect_count(1)
    expect(page.locator("span").filter(has_text=re.compile(r"^Bob, Jones"))).not_to_be_visible()
    recipient_summary.click_add_another_no()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="Alicia, Smith", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Bob, Jones", exact=False)).not_to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)

    # Scenario 2
    tasklist_page.click_on_section(address_section_name)
    address_summary = RunnerAddAnotherSummaryPage(page, domain, handle.grant_name, "Address")
    address_summary.expect_empty()
    address_summary.click_add_first_answer()

    fill_entry(page, domain, handle.grant_name, add_another_all_on_same_page_group, answer_index=0)

    address_summary.expect_count(1)
    address_summary.click_add_another_yes()

    fill_entry(page, domain, handle.grant_name, add_another_all_on_same_page_group, answer_index=1)

    address_summary.expect_count(2)
    address_summary.click_add_another_no()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="123 Fake Street, London", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="456 Real Road, Manchester", exact=False)).to_be_visible()

    page.get_by_role("link", name="Back").click()
    address_summary.click_change(index=0)

    address_page = RunnerQuestionPage(page, domain, handle.grant_name, "Street", is_in_a_same_page_group=True)
    address_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "Street", "789 New Lane")
    address_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "City", "Bristol")
    address_page.click_continue()

    expect(page.locator("span").filter(has_text=re.compile(r"^789 New Lane"))).to_be_visible()
    address_summary.click_remove_last()

    remove_page = RunnerAddAnotherRemovePage(page, domain, handle.grant_name)
    remove_page.confirm_remove()

    address_summary.expect_count(1)
    expect(page.locator("span").filter(has_text=re.compile(r"^456 Real Road"))).not_to_be_visible()
    address_summary.click_add_another_no()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="789 New Lane, Bristol", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="456 Real Road, Manchester", exact=False)).not_to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)

    # Scenario 3
    tasklist_page.click_on_section(organisation_section_name)
    organisation_summary = RunnerAddAnotherSummaryPage(page, domain, handle.grant_name, "Organisation")
    organisation_summary.expect_empty()
    organisation_summary.click_add_first_answer()

    fill_entry(page, domain, handle.grant_name, add_another_nested_group, answer_index=0)

    organisation_summary.expect_count(1)
    organisation_summary.click_add_another_yes()

    fill_entry(page, domain, handle.grant_name, add_another_nested_group, answer_index=1)

    organisation_summary.expect_count(2)
    organisation_summary.click_add_another_no()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="Acme Corp", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Globex", exact=False)).to_be_visible()

    page.get_by_role("link", name="Back").click()
    organisation_summary.click_change(index=0)

    org_name_page = RunnerQuestionPage(page, domain, handle.grant_name, "Organisation name")
    expect(org_name_page.heading).to_be_visible()
    org_name_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "Organisation name", "Acme Corp Ltd")
    org_name_page.click_continue()

    contact_page = RunnerQuestionPage(page, domain, handle.grant_name, "Contact name", is_in_a_same_page_group=True)
    contact_page.respond_to_question(QuestionDataType.TEXT_SINGLE_LINE, "Contact name", "Alice Jones")
    contact_page.respond_to_question(QuestionDataType.EMAIL, "Contact email", "alice.jones@example.com")
    contact_page.click_continue()

    expect(page.locator("span").filter(has_text=re.compile(r"^Acme Corp Ltd"))).to_be_visible()
    organisation_summary.click_remove_last()

    remove_page = RunnerAddAnotherRemovePage(page, domain, handle.grant_name)
    remove_page.confirm_remove()

    organisation_summary.expect_count(1)
    expect(page.locator("span").filter(has_text=re.compile(r"^Globex"))).not_to_be_visible()
    organisation_summary.click_add_another_no()

    check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, handle.grant_name)
    expect(check_your_answers_page.heading).to_be_visible()
    expect(page.get_by_role("heading", name="Acme Corp Ltd", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Globex", exact=False)).not_to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)

    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
