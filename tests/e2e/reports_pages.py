from __future__ import annotations

import re
from typing import cast

from playwright.sync_api import Locator, Page, expect

from app.common.data.types import ManagedExpressionsEnum, MultilineTextInputRows, NumberInputWidths, QuestionDataType
from app.common.expressions.managed import GreaterThan, LessThan, ManagedExpression
from tests.e2e.dataclasses import GuidanceText


class ReportsBasePage:
    domain: str
    page: Page

    heading: Locator
    grant_name: str

    def __init__(self, page: Page, domain: str, heading: Locator, grant_name: str) -> None:
        self.page = page
        self.domain = domain
        self.heading = heading
        self.grant_name = grant_name


class GrantReportsPage(ReportsBasePage):
    add_report_button: Locator
    summary_row_submissions: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} Reports")
        )
        self.add_report_button = self.page.get_by_role("button", name="Add a monitoring report").or_(
            self.page.get_by_role("button", name="Add another monitoring report")
        )
        self.summary_row_submissions = page.locator("div.govuk-summary-list__row").filter(
            has=page.get_by_text("Submissions")
        )

    def click_add_report(self) -> AddReportPage:
        self.add_report_button.click()
        add_report_page = AddReportPage(self.page, self.domain, grant_name=self.grant_name)
        expect(add_report_page.heading).to_be_visible()
        return add_report_page

    def check_report_exists(self, report_name: str) -> None:
        expect(self.page.get_by_role("heading", name=report_name)).to_be_visible()

    def click_add_task(self, report_name: str, grant_name: str) -> AddTaskPage:
        self.page.get_by_role("link", name=f"Add tasks to {report_name}").click()
        add_task_page = AddTaskPage(
            self.page,
            self.domain,
            grant_name=grant_name,
            report_name=report_name,
        )
        expect(add_task_page.heading).to_be_visible()
        return add_task_page

    def click_manage_tasks(self, report_name: str, grant_name: str) -> ReportTasksPage:
        self.page.get_by_role("link", name=re.compile(r"\d+ tasks")).click()
        report_tasks_page = ReportTasksPage(self.page, self.domain, grant_name=grant_name, report_name=report_name)
        expect(report_tasks_page.heading).to_be_visible()
        return report_tasks_page

    def click_view_submissions(self, report_name: str) -> SubmissionsListPage:
        self.summary_row_submissions.get_by_role("link", name="1 test submission").click()
        submissions_list_page = SubmissionsListPage(self.page, self.domain, self.grant_name, report_name)
        expect(submissions_list_page.heading).to_be_visible()
        return submissions_list_page

    def click_change_name(self, report_name: str, grant_name: str) -> ChangeReportNamePage:
        self.page.get_by_role("link", name="Change name").click()
        change_report_name_page = ChangeReportNamePage(self.page, self.domain, self.grant_name)
        expect(change_report_name_page.heading).to_be_visible()
        return change_report_name_page

    def delete_report(self, report_name: str, grant_name: str) -> GrantReportsPage:
        self.page.get_by_role("link", name="Delete").click()
        self.page.get_by_role("button", name="Yes, delete this report").click()
        reports_page = GrantReportsPage(self.page, self.domain, grant_name=grant_name)
        expect(reports_page.heading).to_be_visible()
        return reports_page


class AddReportPage(ReportsBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the monitoring report?"),
        )

    def fill_in_report_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the monitoring report?").fill(name)

    def click_submit(self, grant_name: str) -> GrantReportsPage:
        self.page.get_by_role("button", name="Set up report").click()
        reports_page = GrantReportsPage(self.page, self.domain, grant_name=grant_name)
        expect(reports_page.heading).to_be_visible()
        return reports_page


class ChangeReportNamePage(ReportsBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Change the name for this monitoring report"),
        )

    def fill_in_report_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="Change the name for this monitoring report").fill(name)

    def click_submit(self, grant_name: str) -> GrantReportsPage:
        self.page.get_by_role("button", name="Update report name").click()
        reports_page = GrantReportsPage(self.page, self.domain, grant_name=grant_name)
        expect(reports_page.heading).to_be_visible()
        return reports_page

    def click_cancel(self, grant_name: str) -> GrantReportsPage:
        self.page.get_by_role("link", name="Cancel").click()
        reports_page = GrantReportsPage(self.page, self.domain, grant_name=grant_name)
        expect(reports_page.heading).to_be_visible()
        return reports_page

    def click_back(self, grant_name: str) -> GrantReportsPage:
        self.page.get_by_role("link", name="Back").click()
        reports_page = GrantReportsPage(self.page, self.domain, grant_name=grant_name)
        expect(reports_page.heading).to_be_visible()
        return reports_page


class ReportTasksPage(ReportsBasePage):
    report_name: str
    preview_report_button: Locator
    reports_breadcrumb: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Tasks"),
        )
        self.report_name = report_name
        self.preview_report_button = self.page.get_by_role("button", name="Preview report")
        self.reports_breadcrumb = self.page.locator("a.govuk-breadcrumbs__link").filter(has=page.get_by_text("Reports"))

    def click_reports_breadcrumb(self) -> "GrantReportsPage":
        self.reports_breadcrumb.click()
        grant_reports_page = GrantReportsPage(self.page, self.domain, grant_name=self.grant_name)
        return grant_reports_page

    def check_task_exists(self, task_title: str) -> None:
        expect(self.page.get_by_role("link", name=task_title, exact=True)).to_be_visible()

    def click_preview_report(self) -> RunnerTasklistPage:
        self.preview_report_button.click()
        tasklist_page = RunnerTasklistPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(tasklist_page.heading).to_be_visible()
        return tasklist_page

    def click_manage_task(self, task_name: str) -> ManageTaskPage:
        self.page.get_by_role("link", name=task_name, exact=True).click()
        manage_task_page = ManageTaskPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=task_name,
        )
        expect(manage_task_page.heading).to_be_visible()
        return manage_task_page

    def click_add_task(self) -> AddTaskPage:
        self.page.get_by_role("link", name="Add a task").or_(
            self.page.get_by_role("link", name="Add another task")
        ).click()
        task_type_page = AddTaskPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
        )
        expect(task_type_page.heading).to_be_visible()
        return task_type_page


class ManageTaskPage(ReportsBasePage):
    report_name: str
    task_name: str
    preview_task_button: Locator
    add_question_button: Locator
    change_task_name_link: Locator
    delete_task_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, task_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{task_name}"),
        )
        self.report_name = report_name
        self.task_name = task_name
        self.preview_task_button = self.page.get_by_role("button", name="Preview task")
        self.add_question_button = self.page.get_by_role("link", name="Add a question", exact=True).or_(
            self.page.get_by_role("link", name="Add another question")
        )
        self.change_task_name_link = self.page.get_by_role("link", name="Change task name")
        self.delete_task_link = self.page.get_by_role("button", name="Delete task")

    def click_add_question(self) -> SelectQuestionTypePage:
        self.add_question_button.click()

        select_question_type_page = SelectQuestionTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(select_question_type_page.heading).to_be_visible()
        return select_question_type_page

    def check_question_exists(self, question_name: str) -> None:
        expect(self.page.get_by_role("term").filter(has_text=question_name)).to_be_visible()

    def click_edit_question(self, question_name: str) -> "EditQuestionPage":
        self.page.get_by_role("link", name=question_name, exact=True).click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class EditQuestionPage(ReportsBasePage):
    task_breadcrumb: Locator
    add_validation_button: Locator
    add_guidance_button: Locator
    change_guidance_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, task_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Edit question"),
        )
        self.report_name = report_name
        self.task_name = task_name
        self.task_breadcrumb = self.page.locator("a.govuk-breadcrumbs__link").filter(
            has=page.get_by_text(f"{task_name}")
        )
        self.add_validation_button = self.page.get_by_role("button", name="Add validation").or_(
            self.page.get_by_role("button", name="Add more validation")
        )
        self.add_guidance_button = self.page.get_by_role("link", name="Add guidance")
        self.change_guidance_link = self.page.get_by_role("link", name="Change  page heading")

    def click_add_validation(self) -> "AddValidationPage":
        self.add_validation_button.click()
        add_validation_page = AddValidationPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(add_validation_page.heading).to_be_visible()
        return add_validation_page

    def click_task_breadcrumb(self) -> "ManageTaskPage":
        self.task_breadcrumb.click()
        manage_task_page = ManageTaskPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(manage_task_page.heading).to_be_visible()
        return manage_task_page

    def click_return_to_task(self) -> ManageTaskPage:
        self.page.get_by_role("link", name="Return to the task").click()
        manage_task_page = ManageTaskPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(manage_task_page.heading).to_be_visible()
        return manage_task_page

    def click_save(self) -> ManageTaskPage:
        self.page.get_by_role("button", name="Save").click()
        manage_task_page = ManageTaskPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(manage_task_page.heading).to_be_visible()
        return manage_task_page

    def click_add_guidance(self) -> AddGuidancePage:
        self.add_guidance_button.click()
        add_guidance_page = AddGuidancePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(add_guidance_page.heading).to_be_visible()
        return add_guidance_page

    def click_change_guidance(self) -> AddGuidancePage:
        self.change_guidance_link.click()
        add_guidance_page = AddGuidancePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(add_guidance_page.heading).to_be_visible()
        return add_guidance_page


class AddGuidancePage(ReportsBasePage):
    save_guidance_button: Locator
    preview_guidance_tab: Locator
    write_guidance_tab: Locator
    h2_button: Locator
    link_button: Locator
    bulleted_list_button: Locator
    numbered_list_button: Locator
    guidance_heading_textbox: Locator
    guidance_body_textbox: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, task_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add guidance").or_(
                page.get_by_role("heading", name="Edit guidance")
            ),
        )
        self.report_name = report_name
        self.task_name = task_name
        self.save_guidance_button = self.page.get_by_role("button", name="Save guidance")
        self.preview_guidance_tab = self.page.get_by_role("tab", name="Preview guidance")
        self.write_guidance_tab = self.page.get_by_role("tab", name="Write guidance")
        self.h2_button = self.page.get_by_role("button", name="Add a second-level heading")
        self.link_button = self.page.get_by_role("button", name="Add a link")
        self.bulleted_list_button = self.page.get_by_role("button", name="Add a bulleted list")
        self.numbered_list_button = self.page.get_by_role("button", name="Add a numbered list")
        self.guidance_heading_textbox = self.page.get_by_role("textbox", name="Give your page a heading")
        self.guidance_body_textbox = self.page.get_by_role("textbox", name="Add guidance text")

    def fill_guidance_heading(self, text: str) -> None:
        self.guidance_heading_textbox.fill(text)

    def fill_guidance_text(self, text: str) -> None:
        self.guidance_body_textbox.type(text)

    def go_to_end_of_guidance_text(self) -> None:
        self.guidance_body_textbox.focus()
        self.page.keyboard.press("ControlOrMeta+ArrowDown")

    def add_linebreaks_to_guidance_text(self) -> None:
        self.go_to_end_of_guidance_text()
        self.page.keyboard.press("Enter")
        self.page.keyboard.press("Enter")

    def clear_guidance_heading(self) -> None:
        self.guidance_heading_textbox.clear()

    def clear_guidance_body(self) -> None:
        self.guidance_body_textbox.clear()

    def click_h2_button(self) -> None:
        self.h2_button.click()

    def click_link_button(self) -> None:
        self.link_button.click()

    def click_bulleted_list_button(self) -> None:
        self.bulleted_list_button.click()

    def click_numbered_list_button(self) -> None:
        self.numbered_list_button.click()

    def click_preview_guidance_tab(self) -> None:
        self.preview_guidance_tab.click()

    def click_write_guidance_tab(self) -> None:
        self.write_guidance_tab.click()

    def click_save_guidance_button(self) -> EditQuestionPage:
        self.save_guidance_button.click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page

    def fill_guidance(self, question_definition_guidance: GuidanceText) -> None:
        self.clear_guidance_heading()
        self.clear_guidance_body()
        self.fill_guidance_heading(question_definition_guidance.heading)
        self.fill_guidance_text(f"## {question_definition_guidance.body_heading}")
        self.add_linebreaks_to_guidance_text()
        self.fill_guidance_text(
            f"[{question_definition_guidance.body_link_text}]({question_definition_guidance.body_link_url})"
        )
        self.add_linebreaks_to_guidance_text()
        self.fill_guidance_text("\n".join(f"* {item}" for item in question_definition_guidance.body_ul_items))
        self.add_linebreaks_to_guidance_text()
        self.fill_guidance_text(
            "\n".join(f"{i + 1}. {item}" for i, item in enumerate(question_definition_guidance.body_ol_items))
        )

    def fill_guidance_default(self) -> None:
        self.click_h2_button()
        self.add_linebreaks_to_guidance_text()
        self.click_link_button()
        self.add_linebreaks_to_guidance_text()
        self.click_bulleted_list_button()
        self.add_linebreaks_to_guidance_text()
        self.click_numbered_list_button()
        self.click_preview_guidance_tab()
        expect(self.page.get_by_role("heading", name="Heading text")).to_be_visible()
        expect(self.page.get_by_role("link", name="Link text")).to_be_visible()
        expect(self.page.get_by_role("link", name="Link text")).to_have_attribute(
            "href", "https://www.gov.uk/link-text-url"
        )
        expect(self.page.get_by_label("Preview guidance").locator("ul").get_by_text("List item")).to_be_visible()
        expect(self.page.get_by_label("Preview guidance").locator("ol").get_by_text("List item")).to_be_visible()
        self.click_write_guidance_tab()


class AddValidationPage(ReportsBasePage):
    add_validation_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, task_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add validation"),
        )
        self.report_name = report_name
        self.task_name = task_name
        self.add_validation_button = self.page.get_by_role("button", name="Add validation")

    def configure_managed_validation(self, managed_validation: ManagedExpression) -> None:
        self.click_managed_validation_type(managed_validation)

        match managed_validation._key:
            case ManagedExpressionsEnum.GREATER_THAN:
                managed_validation = cast(GreaterThan, managed_validation)
                self.page.get_by_role("textbox", name="Minimum value").fill(str(managed_validation.minimum_value))

                if managed_validation.inclusive:
                    self.page.get_by_role("checkbox", name="An answer of exactly the minimum value is allowed").check()

            case ManagedExpressionsEnum.LESS_THAN:
                managed_validation = cast(LessThan, managed_validation)
                self.page.get_by_role("textbox", name="Maximum value").fill(str(managed_validation.maximum_value))

                if managed_validation.inclusive:
                    self.page.get_by_role("checkbox", name="An answer of exactly the maximum value is allowed").check()

    def click_managed_validation_type(self, managed_validation: ManagedExpression) -> None:
        self.page.get_by_role("radio", name=managed_validation._key.value).click()

    def click_add_validation(self) -> "EditQuestionPage":
        self.add_validation_button.click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class SelectQuestionTypePage(ReportsBasePage):
    report_name: str
    task_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, task_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What type of question do you need?"),
        )
        self.report_name = report_name
        self.task_name = task_name

    def click_question_type(self, question_type: str) -> None:
        self.page.get_by_role("radio", name=question_type).click()

    def click_continue(self) -> AddQuestionDetailsPage:
        self.page.get_by_role("button", name="Continue").click()
        question_details_page = AddQuestionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(question_details_page.heading).to_be_visible()
        return question_details_page


class AddQuestionDetailsPage(ReportsBasePage):
    report_name: str
    task_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, task_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add question"),
        )
        self.report_name = report_name
        self.task_name = task_name

    def fill_question_text(self, question_text: str) -> None:
        self.page.get_by_role("textbox", name="Question text").fill(question_text)

    def fill_question_name(self, question_name: str) -> None:
        self.page.get_by_role("textbox", name="Question name").fill(question_name)

    def fill_question_hint(self, question_hint: str) -> None:
        self.page.get_by_role("textbox", name="Question hint").fill(question_hint)

    def fill_data_source_items(self, items: list[str]) -> None:
        self.page.get_by_role("textbox", name="List of options").fill("\n".join(items))

    def click_other_option_checkbox(self) -> None:
        self.page.get_by_role("checkbox", name="Include an ‘other’ option").click()

    def enter_other_option_text(self, text: str = "Other") -> None:
        self.page.get_by_role("textbox", name="‘Other’ option text").fill(text)

    def click_advanced_formatting_options(self) -> None:
        self.page.get_by_text("Advanced formatting options").click()

    def fill_word_limit(self, word_limit: int) -> None:
        self.page.get_by_role("textbox", name="Word limit").fill(str(word_limit))

    def fill_prefix(self, text: str) -> None:
        self.page.get_by_role("textbox", name="Prefix").fill(text)

    def fill_suffix(self, text: str) -> None:
        self.page.get_by_role("textbox", name="Suffix").fill(text)

    def select_input_width(self, width: NumberInputWidths) -> None:
        self.page.get_by_label("width").select_option(width.name.title())

    def select_multiline_input_rows(self, rows: MultilineTextInputRows) -> None:
        self.page.get_by_label("Text area size").select_option(f"{rows.name.title()} ({rows.value} rows)")

    def click_submit(self) -> "EditQuestionPage":
        self.page.get_by_role("button", name="Add question").click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            task_name=self.task_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class AddTaskPage(ReportsBasePage):
    report_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the task?"),
        )
        self.report_name = report_name

    def fill_in_task_name(self, task_name: str) -> None:
        self.page.get_by_role("textbox", name="Task name").fill(task_name)

    def click_add_task(self) -> ReportTasksPage:
        self.page.get_by_role("button", name="Add task").click()
        report_tasks_page = ReportTasksPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(report_tasks_page.heading).to_be_visible()
        return report_tasks_page


class RunnerTasklistPage(ReportsBasePage):
    report_name: str
    submission_status_box: Locator
    submit_button: Locator
    back_link: Locator

    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
        report_name: str,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=report_name),
        )
        self.report_name = report_name
        self.submission_status_box = page.get_by_test_id("submission-status")
        self.submit_button = page.get_by_role("button", name="Submit")
        self.back_link = self.page.get_by_role("link", name="Back")

    def click_on_task(self, task_name: str) -> None:
        self.page.get_by_role("link", name=task_name).click()

    def click_submit(self) -> ReportTasksPage:
        self.submit_button.click()
        report_tasks_page = ReportTasksPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(report_tasks_page.heading).to_be_visible()
        return report_tasks_page

    def click_back(self) -> ReportTasksPage:
        self.back_link.click()
        report_tasks_page = ReportTasksPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(report_tasks_page.heading).to_be_visible()
        return report_tasks_page


class RunnerQuestionPage(ReportsBasePage):
    continue_button: Locator
    question_name: str

    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
        question_name: str,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=question_name),
        )
        self.question_name = question_name
        self.continue_button = page.get_by_role("button", name="Continue")

    def respond_to_question(self, question_type: QuestionDataType, answer: str) -> None:
        if question_type == QuestionDataType.CHECKBOXES:
            for choice in answer:
                self.page.get_by_role("checkbox", name=choice).click()
        elif question_type == QuestionDataType.YES_NO or question_type == QuestionDataType.RADIOS:
            # once we start having multiple of these on a page - enjoy the refactor =]
            accessible_autocomplete = self.page.query_selector("[data-accessible-autocomplete]")
            if accessible_autocomplete:
                # there is a few ms of delay during the call to "enhanceSelectElement" which allows the select
                # being progressively enhanced to be selected before its complete as playwright will act immediately
                # on the role being available - this causes the test to fail particularly when there is network latency.
                # Wait for the full input + options to be loaded before using it
                expect(self.page.locator("[class='autocomplete__wrapper']")).to_be_attached()
                element = self.page.get_by_role("combobox")
                element.click()
                element.fill(answer)
                element.press("Enter")
            else:
                self.page.get_by_role("radio", name=answer).click()
        else:
            self.page.get_by_role("textbox", name=self.question_name).fill(answer)

    def click_continue(
        self,
    ) -> None:
        self.continue_button.click()


class RunnerCheckYourAnswersPage(ReportsBasePage):
    save_and_continue_button: Locator
    mark_as_complete_yes: Locator

    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Check your answers"),
        )
        self.save_and_continue_button = page.get_by_role("button", name="Save and continue")
        self.mark_as_complete_yes = page.get_by_role("radio", name="Yes, I’ve completed this task")

    def click_mark_as_complete_yes(self) -> None:
        self.mark_as_complete_yes.click()

    def click_save_and_continue(self, report_name: str) -> RunnerTasklistPage:
        self.save_and_continue_button.click()
        task_list_page = RunnerTasklistPage(self.page, self.domain, self.grant_name, report_name=report_name)
        expect(task_list_page.heading).to_be_visible()
        return task_list_page


class SubmissionsListPage(ReportsBasePage):
    report_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{report_name} Monitoring Reports"),
        )
        self.report_name = report_name

    def click_on_first_submission(self) -> ViewSubmissionPage:
        first_submission_reference = self.page.locator("[data-submission-link]").first.inner_text()
        return self.click_on_submission(first_submission_reference)

    def click_on_submission(self, report_reference: str) -> ViewSubmissionPage:
        self.page.get_by_role("link", name=report_reference).click()
        view_submission_page = ViewSubmissionPage(
            self.page, self.domain, self.grant_name, report_reference=report_reference
        )
        expect(view_submission_page.heading).to_be_visible()
        return view_submission_page


class ViewSubmissionPage(ReportsBasePage):
    report_reference: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_reference: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Submission"),
        )
        self.report_reference = report_reference

    def get_questions_list_for_task(self, task_name: str) -> Locator:
        return self.page.get_by_test_id(task_name)
