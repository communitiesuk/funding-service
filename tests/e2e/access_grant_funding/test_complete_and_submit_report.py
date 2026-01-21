import re
from typing import cast

import pytest
from playwright.sync_api import Page, expect

from app import QuestionDataType
from tests.e2e.access_grant_funding.pages import AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.deliver_grant_funding.reports_pages import (
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
    RunnerTasklistPage,
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import (
    TQuestionToTest,
    assert_check_your_answer_for_all_questions,
)

_shared_access_data = {
    "grant_name": "Cheeseboards in parks",
    "organisation_name": "MHCLG Funding Service Test Organisation",
    "report_name": "Q2 2025",
    "service_name": "MHCLG Funding Service",
    "sections": [
        {
            "name": "Cheese",
            "questions": [
                {
                    "text": "What was the most popular type of cheese in this period?",
                    "type": QuestionDataType.CHECKBOXES,
                    "answers": ["Cheddar"],
                }
            ],
        }
    ],
}


@pytest.mark.authenticate_as("fsd-post-award@levellingup.gov.uk")
@pytest.mark.xfail(reason="Needs to work with the grant and report just created in the deliver tests")
def test_complete_and_submit_report(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_magic_link: E2ETestUser,
    email: str,
) -> None:
    data = _shared_access_data
    access_home_page = AccessHomePage(page, domain)
    access_grant_page = access_home_page.select_grant(data["organisation_name"], data["grant_name"])
    expected_url_pattern = rf"^{domain}/access/organisation/[a-f0-9-]{{36}}/grants/[a-f0-9-]{{36}}/reports[#]?$"

    # JavaScript on the page automatically claims the link and should redirect to where they started.
    expect(page).to_have_url(re.compile(expected_url_pattern))

    access_grant_page.click_collection(data["report_name"])

    expect(page).to_have_title(f"{data['report_name']} - {data['grant_name']} - {data['service_name']}")
    runner_task_list_page = RunnerTasklistPage(
        page, domain, report_name=data["report_name"], grant_name=data["grant_name"]
    )
    # Check the tasklist has loaded
    expect(
        runner_task_list_page.submission_status_box.filter(has=runner_task_list_page.page.get_by_text("Not started"))
    ).to_be_visible()

    for section in data["sections"]:
        runner_task_list_page.click_on_section(str(section["text"]))
        for question in section["questions"]:
            question = cast(TQuestionToTest, question)
            question_page = RunnerQuestionPage(
                page, domain, grant_name=data["grant_name"], question_name=question["text"]
            )
            expect(question_page.heading).to_be_visible()
            question_page.respond_to_question(question["type"], question["text"], question["answers"])
            question_page.click_continue()

        check_your_answers_page = RunnerCheckYourAnswersPage(page, domain, data["grant_name"])
        assert_check_your_answer_for_all_questions(section["questions"], check_your_answers_page)
        check_your_answers_page.click_mark_as_complete_yes()
        check_your_answers_page.click_save_and_continue()

    # TODO this doesn't work after first run because the report is already complete/in progress. Need to make it use
    #  a report just created in the deliver tests
