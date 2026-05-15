import re
from decimal import Decimal
from typing import cast

import pytest
from playwright.sync_api import Locator, Page, expect

from app import NumberTypeEnum, QuestionDataType, format_thousands
from app.common.data.types import GroupDisplayOptions, QuestionPresentationOptions
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import ManagedExpression
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import DeliverGrantFundingUserType, login_with_session_cookie, login_with_stub_sso
from tests.e2e.dataclasses import (
    E2EManagedExpression,
    E2ETestUser,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    TQuestionToTest,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDashboardPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AddConditionPage,
    AddQuestionDetailsPage,
    CreateCalculatedConditionPage,
    CreateCustomExpressionPage,
    EditQuestionGroupPage,
    EditQuestionPage,
    ManageSectionPage,
    ReportSectionsPage,
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
    RunnerTasklistPage,
    _reference_data_flow,
)
from tests.e2e.helpers import wait_for_context_aware_textarea_to_be_ready


def create_grant(new_grant_name: str, grant_name_uuid: str, all_grants_page: AllGrantsPage) -> GrantDashboardPage:
    grant_intro_page = all_grants_page.click_set_up_a_grant()
    grant_ggis_page = grant_intro_page.click_continue()
    grant_ggis_page.select_yes()
    grant_ggis_page.fill_ggis_number()
    grant_name_page = grant_ggis_page.click_save_and_continue()
    grant_name_page.fill_name(new_grant_name)
    grant_code_page = grant_name_page.click_save_and_continue()
    grant_code_page.fill_code(f"E2E-{grant_name_uuid[:8].upper()}")
    grant_description_page = grant_code_page.click_save_and_continue()
    new_grant_description = f"Description for {new_grant_name}"
    grant_description_page.fill_description(new_grant_description)
    grant_contact_page = grant_description_page.click_save_and_continue()
    grant_contact_page.fill_contact_name()
    grant_contact_page.fill_contact_email()
    grant_check_your_answers_page = grant_contact_page.click_save_and_continue()
    grant_dashboard_page = grant_check_your_answers_page.click_add_grant()
    return grant_dashboard_page


def extract_uuid_from_url(url: str, pattern: str) -> str:
    """Extract a UUID from a URL using a regex pattern.

    The pattern should contain a named group 'uuid' for the UUID to extract.
    Example: r"/grant/(?P<uuid>[a-f0-9-]+)/reports"
    """
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Could not extract UUID from URL {url} using pattern {pattern}")
    return match.group("uuid")


def navigate_to_report_sections_page(page: Page, domain: str, grant_name: str, report_name: str) -> ReportSectionsPage:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    report_sections_page = grant_reports_page.click_manage_sections(grant_name=grant_name, report_name=report_name)
    return report_sections_page


def create_question_or_group(
    question_definition: TQuestionToTest,
    manage_section_page: ManageSectionPage | EditQuestionGroupPage,
    parent_group_name: str | None = None,
    parent_add_another: bool = False,
):
    if question_definition["type"] == "group":
        group_definition = cast(QuestionGroupDict, question_definition)
        add_question_group_page = manage_section_page.click_add_question_group(group_definition["text"])
        add_question_group_page.fill_in_question_group_name()
        group_display_options_page = add_question_group_page.click_continue()
        group_display_options_page.click_question_group_display_type(group_definition["display_options"])

        if parent_add_another and parent_group_name is not None:
            edit_question_group_page = group_display_options_page.click_submit_nested(parent_group_name)
        else:
            add_another_options_page = group_display_options_page.click_submit()
            add_another_options_page.click_add_another(group_definition.get("add_another", False))
            edit_question_group_page = add_another_options_page.click_submit(parent_group_name)
        if (
            group_definition.get("guidance") is not None
            and group_definition.get("display_options") == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        ):
            add_question_guidance(group_definition, edit_question_group_page)
        if group_definition.get("condition") is not None:
            add_condition(edit_question_group_page, group_definition["condition"])
        for question in group_definition["questions"]:
            create_question_or_group(
                question,
                edit_question_group_page,
                parent_group_name=group_definition["text"],
                parent_add_another=group_definition.get("add_another", False),
            )
        if group_definition.get("validation") is not None:
            add_calculated_group_validation(edit_question_group_page, group_definition["validation"])
        if parent_group_name:
            edit_question_group_page.click_parent_group_breadcrumb()
        else:
            edit_question_group_page.click_section_breadcrumb()
    else:
        create_question(question_definition, manage_section_page, parent_group_name=parent_group_name)


def _assert_reports_breadcrumb_layout(page: Page, parent_group_name: str | None = None) -> None:
    breadcrumbs = page.locator("a.govuk-breadcrumbs__link")
    if not parent_group_name:
        expect(breadcrumbs).to_have_count(3)
        expect(page.get_by_text("question group hidden ...")).not_to_be_visible()
    elif parent_group_name == "This is a question group" or parent_group_name == "One question per page group":
        expect(breadcrumbs).to_have_count(4)
        expect(page.get_by_text("question group hidden ...")).not_to_be_visible()
    elif parent_group_name == "Nested Group":
        expect(breadcrumbs).to_have_count(4)
        expect(page.get_by_text("question group hidden ...")).to_be_visible()


def create_question(
    question_definition: QuestionDict,
    manage_page: ManageSectionPage | EditQuestionGroupPage,
    parent_group_name: str | None = None,
) -> None:
    question_type_page = manage_page.click_add_question()
    question_type_page.click_question_type(question_definition["type"])
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_definition["type"].value, exact=True)).to_be_visible()
    question_text = question_definition["text"]
    wait_for_context_aware_textarea_to_be_ready(question_details_page.page, "text")
    wait_for_context_aware_textarea_to_be_ready(question_details_page.page, "hint")

    if question_definition["type"] == QuestionDataType.NUMBER:
        question_details_page.select_number_type(
            question_definition["data_options"].number_type  # ty:ignore[invalid-argument-type]
        )
        if question_definition["data_options"].number_type == NumberTypeEnum.DECIMAL:
            question_details_page.fill_max_number_of_decimal_places(
                question_definition["data_options"].max_decimal_places  # ty:ignore[invalid-argument-type]
            )

    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(question_text.lower())

    if hint := question_definition.get("hint"):
        question_details_page.fill_question_hint(hint.prefix)
        select_data_source_page = question_details_page.click_insert_data(field_name="hint")
        _reference_data_flow(select_data_source_page, hint.data_reference)
    else:
        question_details_page.fill_question_hint(f"Hint text for: {question_text}")

    if question_definition["type"] in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
        question_details_page.fill_data_source_items(question_definition["choices"])

        options = question_definition.get("options")
        if options is not None and options.last_data_source_item_is_distinct_from_others is not None:
            question_details_page.click_other_option_checkbox()
            question_details_page.enter_other_option_text()

    if (
        question_definition["type"]
        in [QuestionDataType.NUMBER, QuestionDataType.TEXT_MULTI_LINE, QuestionDataType.DATE]
        and question_definition.get("options") is not None
    ):
        add_advanced_formatting(question_definition, question_details_page)

    edit_question_page = question_details_page.click_submit()

    _assert_reports_breadcrumb_layout(edit_question_page.page, parent_group_name=parent_group_name)

    if question_definition.get("guidance") is not None:
        add_question_guidance(question_definition, edit_question_page)
    if question_definition.get("validation") is not None:
        add_validation(
            edit_question_page,
            question_definition["validation"],
            question_definition.get("options", None),
        )
    if question_definition.get("condition") is not None:
        add_condition(edit_question_page, question_definition["condition"], question_definition.get("options", None))

    if isinstance(manage_page, EditQuestionGroupPage):
        edit_question_page.click_question_group_breadcrumb(manage_page.group_name)
    else:
        edit_question_page.click_section_breadcrumb()


def add_advanced_formatting(
    question_definition: TQuestionToTest, question_details_page: AddQuestionDetailsPage
) -> None:
    options = question_definition.get("options")
    question_details_page.click_advanced_formatting_options()
    if not isinstance(options, QuestionPresentationOptions):
        return
    match question_definition["type"]:
        case QuestionDataType.TEXT_MULTI_LINE:
            if options.rows is not None:
                question_details_page.select_multiline_input_rows(options.rows)
            if options.word_limit is not None:
                question_details_page.fill_word_limit(options.word_limit)
        case QuestionDataType.NUMBER:
            if options.prefix is not None:
                question_details_page.fill_prefix(options.prefix)
            if options.suffix is not None:
                question_details_page.fill_suffix(options.suffix)
            if options.width is not None:
                question_details_page.select_input_width(options.width)
        case QuestionDataType.DATE:
            if options.approximate_date:
                question_details_page.click_is_approximate_date_checkbox()
        case _:
            pass  # No advanced formatting for other question types


def add_question_guidance(
    question_definition: TQuestionToTest, edit_question_page: EditQuestionPage | EditQuestionGroupPage
) -> None:
    guidance = question_definition.get("guidance")
    if guidance is not None:
        add_guidance_page = edit_question_page.click_add_guidance()
        add_guidance_page.fill_guidance_heading(guidance.heading)
        wait_for_context_aware_textarea_to_be_ready(add_guidance_page.page, "guidance_body")
        add_guidance_page.fill_guidance_default()
        edit_question_page = add_guidance_page.click_save_guidance_button(edit_question_page)
        expect(edit_question_page.page.get_by_text("Page heading", exact=True)).to_be_visible()
        expect(edit_question_page.page.get_by_text("Guidance text", exact=True)).to_be_visible()
        edit_question_page.click_change_guidance()
        add_guidance_page.fill_guidance(guidance)
        add_guidance_page.click_save_guidance_button(edit_question_page)


def add_calculated_group_validation(
    edit_question_group_page: EditQuestionGroupPage,
    validation: E2EManagedExpression,
) -> None:
    if not isinstance(validation.evaluatable_expression, CustomExpression):
        pytest.fail("Unexpected evaluatable expression, expected CustomExpression")
    add_validation_page = edit_question_group_page.click_add_validation()
    add_validation_page.configure_custom_expression(
        validation.evaluatable_expression.custom_expression, validation.expression_references
    )
    if validation.evaluatable_expression.custom_message:
        add_validation_page.configure_custom_message(
            validation.evaluatable_expression.custom_message, validation.expression_references
        )
    add_validation_page.click_create_group_validation_expression()


def add_validation(
    edit_question_page: EditQuestionPage,
    validation: E2EManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    add_validation_page = edit_question_page.click_add_validation()
    if isinstance(validation.evaluatable_expression, CustomExpression):
        add_validation_page.click_calculation_option()
        add_custom_validation_page = cast(CreateCustomExpressionPage, add_validation_page.click_add_validation())

        add_custom_validation_page.configure_custom_expression(
            validation.evaluatable_expression.custom_expression, validation.expression_references
        )
        if validation.evaluatable_expression.custom_message:
            add_custom_validation_page.configure_custom_message(
                validation.evaluatable_expression.custom_message, validation.expression_references
            )
        add_custom_validation_page.click_create_custom_validation_expression()

    else:
        add_validation_page.configure_managed_validation(
            cast(ManagedExpression, validation.evaluatable_expression), validation.context_source, presentation_options
        )
        add_validation_page.click_add_validation()


def add_condition(
    edit_question_page: EditQuestionPage | EditQuestionGroupPage,
    condition: E2EManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    select_calculation_page = edit_question_page.click_add_condition()
    if isinstance(condition.evaluatable_expression, CustomExpression):
        select_calculation_page.click_yes_need_calculation()
        calculated_condition_page = cast(CreateCalculatedConditionPage, select_calculation_page.click_continue())
        calculated_condition_page.fill_calculation_name(condition.evaluatable_expression.expression_name)  # ty:ignore[invalid-argument-type]
        calculated_condition_page.configure_custom_expression(
            expression=condition.evaluatable_expression.custom_expression,
            expression_references=condition.expression_references,
        )
        calculated_condition_page.click_create_calculated_condition(edit_question_page)
    else:
        select_calculation_page.click_no_calculation()
        add_condition_page = cast(AddConditionPage, select_calculation_page.click_continue())
        select_data_source_page = add_condition_page.click_reference_data_button()
        _reference_data_flow(select_data_source_page, condition.conditional_on)  # ty:ignore[invalid-argument-type]
        add_condition_page.configure_managed_condition(
            cast(ManagedExpression, condition.evaluatable_expression), condition.context_source, presentation_options
        )
        add_condition_page.click_add_condition(edit_question_page)


def answer_questions_and_check_for_expected_errors(
    questions_on_this_page: list[QuestionDict],
    question_page: RunnerQuestionPage,
    group_validation_error: str | None = None,
    same_page_group: bool = False,
):
    for question in questions_on_this_page:
        question_page = RunnerQuestionPage(
            question_page.page,
            question_page.domain,
            question_page.grant_name,
            question["text"],
            is_in_a_same_page_group=same_page_group,
        )
        assert_question_visibility(question_page, question)

    max_answers = max(len(q["answers"]) for q in questions_on_this_page)
    for answer_idx in range(max_answers):
        expect_errors = False
        current_responses: list[QuestionResponse] = []
        for question in questions_on_this_page:
            if "This question should not be shown" in question["display_text"]:
                continue

            # If this question doesn't have as many answers as other questions in the group, just use its last answer
            response = (
                question["answers"][answer_idx]
                if answer_idx < len(question["answers"])
                else question["answers"][len(question["answers"]) - 1]
            )
            current_responses.append(response)
            if response.error_message or response.expect_group_validation_error:
                expect_errors = True
            question_page.respond_to_question(question["type"], question["text"], response.answer)
        question_page.click_continue()
        if expect_errors:
            for response in current_responses:
                if response.error_message is not None:
                    expect(question_page.page.get_by_role("link", name=response.error_message)).to_be_visible()
                if response.expect_group_validation_error and group_validation_error is not None:
                    expect(question_page.page.get_by_text(group_validation_error)).to_be_visible()


def complete_question_group(
    question_page: RunnerQuestionPage,
    tasklist_page: RunnerTasklistPage,
    grant_name: str,
    group_to_test: QuestionGroupDict,
):

    if group_to_test["display_options"] == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE:
        if group_to_test.get("guidance") is not None:
            # Just checks the guidance for this group is visible
            assert_question_visibility(question_page, group_to_test)

        answer_questions_and_check_for_expected_errors(
            group_to_test["questions"],  # ty:ignore[invalid-argument-type]
            question_page,
            group_to_test["validation"].evaluatable_expression.custom_message  # ty:ignore[unresolved-attribute]
            if group_to_test.get("validation") is not None
            else None,
            same_page_group=True,
        )

    else:
        for nested_question in group_to_test["questions"]:
            if nested_question["type"] == "group":
                complete_question_group(
                    question_page, tasklist_page, grant_name, cast(QuestionGroupDict, nested_question)
                )
            else:
                answer_questions_and_check_for_expected_errors(
                    [nested_question],
                    question_page,
                    None,
                )


def complete_task(
    tasklist_page: RunnerTasklistPage, section_name: str, grant_name: str, questions_to_test: list[TQuestionToTest]
) -> None:
    tasklist_page.click_on_section(section_name=section_name)
    for question_to_test in questions_to_test:
        question_page = RunnerQuestionPage(
            tasklist_page.page,
            tasklist_page.domain,
            grant_name,
            question_to_test.get("display_text", question_to_test["text"]),
        )

        if question_to_test["type"] == "group":
            complete_question_group(question_page, tasklist_page, grant_name, cast(QuestionGroupDict, question_to_test))
        else:
            answer_questions_and_check_for_expected_errors([question_to_test], question_page, None)


def task_check_your_answers(
    tasklist_page: RunnerTasklistPage, grant_name: str, report_name: str, questions_to_test: list[TQuestionToTest]
):
    check_your_answers_page = RunnerCheckYourAnswersPage(tasklist_page.page, tasklist_page.domain, grant_name)

    def _assert_check_your_answers(questions_to_check: list[TQuestionToTest]):
        for question_to_check in questions_to_check:
            if question_to_check["type"] == "group":
                _assert_check_your_answers(cast(QuestionGroupDict, question_to_check)["questions"])
            else:
                assert_check_your_answers(check_your_answers_page, question_to_check)

    _assert_check_your_answers(questions_to_test)

    expect(check_your_answers_page.page.get_by_text("Have you completed this section?", exact=True)).to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)


def assert_question_visibility(question_page: RunnerQuestionPage, question_to_test: TQuestionToTest) -> None:
    if display_hint := question_to_test.get("display_hint"):
        expect(question_page.page.locator(".govuk-hint", has_text=display_hint)).to_be_visible()

    if question_to_test.get("guidance") is None:
        if "This question should not be shown" in question_to_test["text"]:
            expect(question_page.heading).not_to_be_visible()
        else:
            expect(question_page.heading).to_be_visible()
    else:
        expect(question_page.page.get_by_role("heading", name=question_to_test["guidance"].heading)).to_be_visible()
        expect(
            question_page.page.get_by_role("heading", name=question_to_test["guidance"].body_heading)
        ).to_be_visible()
        expect(question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)).to_be_visible()
        expect(
            question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)
        ).to_have_attribute("href", question_to_test["guidance"].body_link_url)
        for item in question_to_test["guidance"].body_ul_items:
            expect(question_page.page.locator("ul").get_by_text(item)).to_be_visible()
        for item in question_to_test["guidance"].body_ol_items:
            expect(question_page.page.locator("ol").get_by_text(item)).to_be_visible()


def assert_check_your_answers(check_your_answers_page: RunnerCheckYourAnswersPage, question: QuestionDict) -> None:
    if "This question should not be shown" in question["text"]:
        return

    question_heading = check_your_answers_page.page.get_by_text(question["display_text"], exact=True)
    expect(question_heading).to_be_visible()

    question_name = question["text"].lower()
    if question["type"] == QuestionDataType.CHECKBOXES:
        checkbox_answers_list = check_your_answers_page.page.get_by_test_id(f"answer-{question_name}").locator("li")
        expect(checkbox_answers_list).to_have_text(question["answers"][-1].answer)
    elif question["type"] == QuestionDataType.NUMBER:
        answer_to_format = (
            int(question["answers"][-1].answer)  # ty:ignore[invalid-argument-type]
            if question["data_options"].number_type == NumberTypeEnum.INTEGER
            else Decimal(question["answers"][-1].answer)  # ty:ignore[invalid-argument-type]
        )
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            f"{question['options'].prefix or ''}{format_thousands(answer_to_format)}{question['options'].suffix or ''}"
        )
    elif question["type"] == QuestionDataType.DATE:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            question["answers"][-1].check_your_answers_text  # ty:ignore[invalid-argument-type]
        )
    else:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            question["answers"][-1].answer
        )


def assert_check_your_answer_for_all_questions(questions_to_check: list[TQuestionToTest], report_answers_list: Locator):
    for question_to_check in questions_to_check:
        if question_to_check["type"] == "group":
            assert_check_your_answer_for_all_questions(
                cast(QuestionGroupDict, question_to_check)["questions"], report_answers_list
            )
        else:
            assert_check_your_answer_for_question(question_to_check, report_answers_list)


def assert_check_your_answer_for_question(question: QuestionDict, answers_list: Locator) -> None:
    # TODO Can we combine this with the logic in assert_check_your_answers? Feels like duplication
    if "This question should not be shown" in question["text"]:
        return
    if question["type"] == QuestionDataType.CHECKBOXES:
        expect(
            answers_list.get_by_text(f"{question['text']} {' '.join(question['answers'][-1].answer)}", exact=True)
        ).to_be_visible()
    elif question["type"] == QuestionDataType.NUMBER:
        expect(
            answers_list.get_by_text(
                f"{question['text']} {question['options'].prefix or ''}"
                f"{format_thousands(int(question['answers'][-1].answer))}"  # ty:ignore[invalid-argument-type]
                "{question['options'].suffix or ''}",
                exact=True,
            )
        ).to_be_visible()
    elif question["type"] == QuestionDataType.DATE:
        expect(
            answers_list.get_by_text(
                question["answers"][-1].check_your_answers_text,  # ty:ignore[invalid-argument-type]
                exact=True,
            )
        ).to_be_visible()
    else:
        expect(
            answers_list.get_by_text(f"{question['text']} {question['answers'][-1].answer}", exact=True)
        ).to_be_visible()


def switch_user(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    user_type: DeliverGrantFundingUserType,
    email_address: str,
) -> E2ETestUser:
    grant_dashboard_page = GrantDashboardPage(page, domain)
    grant_dashboard_page.click_sign_out()
    if e2e_test_secrets.E2E_ENV == "local":
        return login_with_stub_sso(domain, page, email_address, user_type)
    else:
        return login_with_session_cookie(page, domain, e2e_test_secrets, user_type)
