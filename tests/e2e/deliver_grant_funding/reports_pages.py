from __future__ import annotations

import datetime
import re
import tempfile
import textwrap
from typing import TYPE_CHECKING, Literal, cast

from playwright.sync_api import Locator, Page, expect

from app.common.data.types import (
    GroupDisplayOptions,
    ManagedExpressionsEnum,
    MultilineTextInputRows,
    NumberInputWidths,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import (
    AnyOf,
    Between,
    BetweenDates,
    GreaterThan,
    LessThan,
    ManagedExpression,
    Specifically,
)
from tests.e2e.dataclasses import DataReferenceConfig, GuidanceText

if TYPE_CHECKING:
    from tests.e2e.deliver_grant_funding.pages import GrantTeamPage, SSOSignInPage


def _reference_data_in_expression(
    expression_form_page: "AddValidationPage" | "AddConditionPage", field_name: str, context_source: DataReferenceConfig
) -> None:
    select_data_source_page = expression_form_page.click_insert_data(field_name)
    select_data_source_page.select_data_source(context_source.data_source)

    match context_source.data_source:
        case (
            ExpressionContext.ContextSources.SECTION
            | ExpressionContext.ContextSources.PREVIOUS_SECTION
            | ExpressionContext.ContextSources.PREVIOUS_COLLECTION
        ):
            if context_source.collection_text:
                raise NotImplementedError("Select previous collection is not yet supported for this context source")

            if context_source.section_text:
                select_section_page = SelectDataSourceSectionPage(
                    select_data_source_page.page,
                    domain=select_data_source_page.domain,
                    grant_name=select_data_source_page.grant_name,
                )
                select_section_page.choose_section(context_source.section_text)

            if context_source.question_text:
                select_question_page: SelectDataSourceQuestionPage = SelectDataSourceQuestionPage(
                    select_data_source_page.page,
                    domain=select_data_source_page.domain,
                    grant_name=select_data_source_page.grant_name,
                )
                select_question_page.choose_question(context_source.question_text)
                select_question_page.click_use_data()

        case _:
            raise NotImplementedError(f"Unsupported context source type: {context_source.data_source}")


def _configure_greater_than_expression(
    expression_form_page: "AddValidationPage" | "AddConditionPage",
    expression: GreaterThan,
    context_source: DataReferenceConfig | None,
) -> None:
    if context_source and expression.minimum_expression == "":
        _reference_data_in_expression(expression_form_page, "minimum value", context_source)
    else:
        expression_form_page.page.get_by_role("textbox", name="Minimum value").fill(str(expression.minimum_value))

    if expression.inclusive:
        expression_form_page.page.get_by_role(
            "checkbox", name="An answer of exactly the minimum value is allowed"
        ).check()


def _configure_less_than_expression(
    expression_form_page: "AddValidationPage" | "AddConditionPage",
    expression: LessThan,
    context_source: DataReferenceConfig | None,
) -> None:
    if context_source and expression.maximum_expression == "":
        _reference_data_in_expression(expression_form_page, "maximum value", context_source)
    else:
        expression_form_page.page.get_by_role("textbox", name="Maximum value").fill(str(expression.maximum_value))

    if expression.inclusive:
        expression_form_page.page.get_by_role(
            "checkbox", name="An answer of exactly the maximum value is allowed"
        ).check()


def _configure_between_expression(
    expression_form_page: "AddValidationPage" | "AddConditionPage",
    expression: Between,
    context_source: DataReferenceConfig | None,
) -> None:
    # Note that the E2EManagedExpression assumes you're only referencing one question's answer in an expression, if two
    # are needed here then the dataclass and this method will need updating
    if context_source and expression.minimum_expression == "":
        _reference_data_in_expression(expression_form_page, "minimum value", context_source)
    else:
        expression_form_page.page.get_by_role("textbox", name="Minimum value").fill(str(expression.minimum_value))

    if context_source and expression.maximum_expression == "":
        _reference_data_in_expression(expression_form_page, "maximum value", context_source)
    else:
        expression_form_page.page.get_by_role("textbox", name="Maximum value").fill(str(expression.maximum_value))

    if expression.minimum_inclusive:
        expression_form_page.page.get_by_role(
            "checkbox", name="An answer of exactly the minimum value is allowed"
        ).check()
    if expression.maximum_inclusive:
        expression_form_page.page.get_by_role(
            "checkbox", name="An answer of exactly the maximum value is allowed"
        ).check()


def _configure_between_dates_expression(
    expression_form_page: "AddValidationPage" | "AddConditionPage",
    expression: BetweenDates,
    presentation_options: QuestionPresentationOptions | None = None,
    context_source: DataReferenceConfig | None = None,
) -> None:
    # Note that the E2EManagedExpression assumes you're only referencing one question's answer in an expression, if two
    # are needed here then the dataclass and this method will need updating
    if context_source and expression.earliest_expression == "":
        _reference_data_in_expression(expression_form_page, "earliest date", context_source)
    else:
        earliest_date_group = expression_form_page.page.get_by_role("group", name="Earliest date")
        ReportsBasePage.fill_in_date_fields(
            earliest_date_group,
            cast(datetime.date, expression.earliest_value),
            approx_date=bool(presentation_options.approximate_date) if presentation_options else False,
        )
    if expression.earliest_inclusive:
        expression_form_page.page.get_by_role(
            "checkbox", name="An answer of exactly the earliest date is allowed"
        ).check()

    if context_source and expression.latest_expression == "":
        _reference_data_in_expression(expression_form_page, "latest date", context_source)
    else:
        latest_date_group = expression_form_page.page.get_by_role("group", name="Latest date")
        ReportsBasePage.fill_in_date_fields(
            latest_date_group,
            cast(datetime.date, expression.latest_value),
            approx_date=bool(presentation_options.approximate_date) if presentation_options else False,
        )
    if expression.latest_inclusive:
        expression_form_page.page.get_by_role(
            "checkbox", name="An answer of exactly the latest date is allowed"
        ).check()


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

    @classmethod
    def fill_in_date_fields(
        cls, date_group: Locator, date_to_complete: datetime.date, approx_date: bool = False
    ) -> None:
        if not approx_date:
            date_group.get_by_label("Day").click()
            date_group.get_by_label("Day").fill(str(date_to_complete.day))
        date_group.get_by_label("Month").click()
        date_group.get_by_label("Month").fill(str(date_to_complete.month))
        date_group.get_by_label("Year").click()
        date_group.get_by_label("Year").fill(str(date_to_complete.year))

    def click_nav_sign_out(self) -> SSOSignInPage:
        from tests.e2e.deliver_grant_funding.pages import SSOSignInPage

        self.page.get_by_role("link", name="Sign out").click()
        sso_sign_in_page = SSOSignInPage(self.page, self.domain)
        return sso_sign_in_page

    def click_nav_grant_team(self) -> GrantTeamPage:
        from tests.e2e.deliver_grant_funding.pages import GrantTeamPage

        self.page.get_by_role("link", name="Team").click()
        sso_sign_in_page = GrantTeamPage(self.page, self.domain)
        return sso_sign_in_page


class DeliverTestGrantRecipientJourneyPage(ReportsBasePage):
    start_button: Locator

    def __init__(self, page: Page, domain: str, grant_id: str, collection_id: str, collection_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name="",
            heading=page.get_by_role("heading", name=f"Test the {collection_name} report"),
        )
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.collection_name = collection_name
        self.start_button = self.page.get_by_role("button", name="Start test submission journey")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/deliver/grant/{self.grant_id}/reports/{self.collection_id}")
        expect(self.heading).to_be_visible()

    def select_test_organisation(self, org_name: str) -> None:
        self.page.get_by_role("radio", name=org_name).check()

    def click_start_test_journey(self) -> None:
        self.start_button.click()
        expect(self.page.get_by_text("We emailed you a link to test the grant recipient journey")).to_be_visible()


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

    def navigate(self, grant_id: str) -> None:
        self.page.goto(f"{self.domain}/deliver/grant/{grant_id}/reports")
        expect(self.heading).to_be_visible()

    def click_add_report(self) -> AddReportPage:
        self.add_report_button.click()
        add_report_page = AddReportPage(self.page, self.domain, grant_name=self.grant_name)
        expect(add_report_page.heading).to_be_visible()
        return add_report_page

    def check_report_exists(self, report_name: str) -> None:
        expect(self.page.get_by_role("heading", name=report_name)).to_be_visible()

    def click_add_section(self, report_name: str, grant_name: str) -> AddSectionPage:
        self.page.get_by_role("link", name=f"Add sections to {report_name}").click()
        add_section_page = AddSectionPage(
            self.page,
            self.domain,
            grant_name=grant_name,
            report_name=report_name,
        )
        expect(add_section_page.heading).to_be_visible()
        return add_section_page

    def click_manage_sections(self, report_name: str, grant_name: str) -> ReportSectionsPage:
        self.page.get_by_role("link", name=re.compile(r"\d+ section")).click()
        report_sections_page = ReportSectionsPage(
            self.page, self.domain, grant_name=grant_name, report_name=report_name
        )
        expect(report_sections_page.heading).to_be_visible()
        return report_sections_page

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


class ReportSectionsPage(ReportsBasePage):
    report_name: str
    preview_report_button: Locator
    reports_breadcrumb: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Sections"),
        )
        self.report_name = report_name
        self.preview_report_button = self.page.get_by_role("button", name="Preview report")
        self.reports_breadcrumb = self.page.locator("a.govuk-breadcrumbs__link").filter(has=page.get_by_text("Reports"))

    def click_reports_breadcrumb(self) -> "GrantReportsPage":
        self.reports_breadcrumb.click()
        grant_reports_page = GrantReportsPage(self.page, self.domain, grant_name=self.grant_name)
        return grant_reports_page

    def check_section_exists(self, section_title: str) -> None:
        expect(self.page.get_by_role("link", name=section_title, exact=True)).to_be_visible()

    def click_preview_report(self) -> RunnerTasklistPage:
        self.preview_report_button.click()
        tasklist_page = RunnerTasklistPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(tasklist_page.heading).to_be_visible()
        return tasklist_page

    def click_manage_section(self, section_name: str) -> ManageSectionPage:
        self.page.get_by_role("link", name=section_name, exact=True).click()
        manage_section_page = ManageSectionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=section_name,
        )
        expect(manage_section_page.heading).to_be_visible()
        return manage_section_page

    def click_add_section(self) -> AddSectionPage:
        self.page.get_by_role("link", name="Add a section").or_(
            self.page.get_by_role("link", name="Add another section")
        ).click()
        add_section_page = AddSectionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
        )
        expect(add_section_page.heading).to_be_visible()
        return add_section_page


class ManageSectionPage(ReportsBasePage):
    report_name: str
    section_name: str
    preview_section_button: Locator
    add_question_button: Locator
    add_question_group_button: Locator
    change_section_name_link: Locator
    delete_section_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{section_name}"),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.preview_section_button = self.page.get_by_role("button", name="Preview section")
        self.add_question_button = self.page.get_by_role("link", name="Add a question", exact=True).or_(
            self.page.get_by_role("link", name="Add another question")
        )
        self.add_question_group_button = self.page.get_by_role("link", name="Add a question group", exact=True)
        self.change_section_name_link = self.page.get_by_role("link", name="Change section name")
        self.delete_section_link = self.page.get_by_role("button", name="Delete section")

    def click_add_question(self) -> SelectQuestionTypePage:
        self.add_question_button.click()

        select_question_type_page = SelectQuestionTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(select_question_type_page.heading).to_be_visible()
        return select_question_type_page

    def click_add_question_group(self, group_name: str) -> AddQuestionGroupPage:
        self.add_question_group_button.click()

        add_question_group_page = AddQuestionGroupPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=group_name,
        )
        expect(add_question_group_page.heading).to_be_visible()
        return add_question_group_page

    def check_question_exists(self, question_name: str) -> None:
        expect(self.page.get_by_role("term").filter(has_text=question_name)).to_be_visible()

    def click_edit_question(self, question_name: str) -> "EditQuestionPage":
        self.page.get_by_role("link", name=question_name, exact=True).click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class EditQuestionPage(ReportsBasePage):
    section_breadcrumb: Locator
    add_validation_button: Locator
    add_condition_button: Locator
    add_guidance_button: Locator
    change_guidance_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Edit question"),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.section_breadcrumb = self.page.locator("a.govuk-breadcrumbs__link").filter(
            has=page.get_by_text(f"{section_name}")
        )
        self.add_validation_button = self.page.get_by_role("button", name="Add validation").or_(
            self.page.get_by_role("button", name="Add more validation")
        )
        self.add_condition_button = self.page.get_by_role("button", name="Add condition")
        self.add_guidance_button = self.page.get_by_role("link", name="Add guidance")
        self.change_guidance_link = self.page.get_by_role("link", name="Change  page heading")

    def click_add_validation(self) -> "AddValidationPage":
        self.add_validation_button.click()
        add_validation_page = AddValidationPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(add_validation_page.heading).to_be_visible()
        return add_validation_page

    def click_add_condition(self) -> "AddConditionPage":
        self.add_condition_button.click()
        add_condition_page = AddConditionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(add_condition_page.heading).to_be_visible()
        return add_condition_page

    def click_section_breadcrumb(self) -> "ManageSectionPage":
        self.section_breadcrumb.click()
        manage_section_page = ManageSectionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(manage_section_page.heading).to_be_visible()
        return manage_section_page

    def click_question_group_breadcrumb(self, question_group_name: str) -> EditQuestionGroupPage:
        self.page.locator("a.govuk-breadcrumbs__link").filter(has=self.page.get_by_text(question_group_name)).click()
        edit_question_group_page = EditQuestionGroupPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=question_group_name,
        )
        expect(edit_question_group_page.heading).to_be_visible()
        return edit_question_group_page

    def click_return_to_section(self) -> ManageSectionPage:
        self.page.get_by_role("link", name="Return to the section").click()
        manage_section_page = ManageSectionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(manage_section_page.heading).to_be_visible()
        return manage_section_page

    def click_save(self) -> ManageSectionPage:
        self.page.get_by_role("button", name="Save").click()
        manage_section_page = ManageSectionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(manage_section_page.heading).to_be_visible()
        return manage_section_page

    def click_add_guidance(self) -> AddGuidancePage:
        self.add_guidance_button.click()
        add_guidance_page = AddGuidancePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
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
            section_name=self.section_name,
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

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add guidance").or_(
                page.get_by_role("heading", name="Edit guidance")
            ),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.save_guidance_button = self.page.get_by_role("button", name="Save guidance")
        self.preview_guidance_tab = self.page.get_by_role("tab", name="Preview guidance")
        self.write_guidance_tab = self.page.get_by_role("tab", name="Write guidance")
        self.h2_button = self.page.get_by_role("button", name="Add a second-level heading")
        self.link_button = self.page.get_by_role("button", name="Add a link")
        self.bulleted_list_button = self.page.get_by_role("button", name="Add a bulleted list")
        self.numbered_list_button = self.page.get_by_role("button", name="Add a numbered list")
        self.guidance_heading_textbox = self.page.get_by_role("textbox", name="Give your page a heading")
        self.guidance_body_textbox = self.page.locator(
            ".app-context-aware-editor__editor-container",
            has=self.page.get_by_role("textbox", name="Add guidance text"),
        ).get_by_role("textbox", name="Add guidance text")

    def fill_guidance_heading(self, text: str) -> None:
        self.guidance_heading_textbox.fill(text)

    def fill_guidance_text(self, text: str) -> None:
        self.guidance_body_textbox.fill(text)
        expect(self.guidance_body_textbox).to_have_value(re.compile(re.escape(text)))

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

    def click_save_guidance_button(
        self, edit_page: EditQuestionPage | EditQuestionGroupPage
    ) -> EditQuestionPage | EditQuestionGroupPage:
        self.save_guidance_button.click()
        if isinstance(edit_page, EditQuestionPage):
            edit_page = EditQuestionPage(
                self.page,
                self.domain,
                grant_name=self.grant_name,
                report_name=self.report_name,
                section_name=self.section_name,
            )
        else:
            edit_page = EditQuestionGroupPage(
                self.page,
                self.domain,
                grant_name=self.grant_name,
                report_name=self.report_name,
                section_name=self.section_name,
                group_name=edit_page.group_name,
            )
        expect(edit_page.heading).to_be_visible()
        return edit_page

    def fill_guidance(self, question_definition_guidance: GuidanceText) -> None:
        self.clear_guidance_heading()
        self.clear_guidance_body()
        self.fill_guidance_heading(question_definition_guidance.heading)
        expect(self.guidance_heading_textbox).to_have_value(question_definition_guidance.heading)

        guidance_text = textwrap.dedent(f"""
        ## {question_definition_guidance.body_heading}

        [{question_definition_guidance.body_link_text}]({question_definition_guidance.body_link_url})

        {"\n        ".join(f"* {item}" for item in question_definition_guidance.body_ul_items)}

        {"\n        ".join(f"{i + 1}. {item}" for i, item in enumerate(question_definition_guidance.body_ol_items))}
        """).strip()

        self.fill_guidance_text(guidance_text)

    def fill_guidance_default(self) -> None:
        self.click_h2_button()
        self.add_linebreaks_to_guidance_text()
        expect(self.guidance_body_textbox).to_have_value(re.compile(re.escape("## Heading text")))

        self.click_link_button()
        self.add_linebreaks_to_guidance_text()
        expect(self.guidance_body_textbox).to_have_value(
            re.compile(re.escape("[Link text](https://www.gov.uk/link-text-url)"))
        )

        self.click_bulleted_list_button()
        self.add_linebreaks_to_guidance_text()
        expect(self.guidance_body_textbox).to_have_value(re.compile(re.escape("* List item")))

        self.click_numbered_list_button()
        expect(self.guidance_body_textbox).to_have_value(re.compile(re.escape("1. List item")))

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

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add validation"),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.add_validation_button = self.page.get_by_role("button", name="Add validation")

    def configure_managed_validation(
        self,
        managed_validation: ManagedExpression,
        context_source: DataReferenceConfig | None = None,
        presentation_options: QuestionPresentationOptions | None = None,
    ) -> None:
        self.click_managed_validation_type(managed_validation)

        match managed_validation._key:
            case ManagedExpressionsEnum.GREATER_THAN:
                managed_validation = cast(GreaterThan, managed_validation)
                _configure_greater_than_expression(self, managed_validation, context_source)

            case ManagedExpressionsEnum.LESS_THAN:
                managed_validation = cast(LessThan, managed_validation)
                _configure_less_than_expression(self, managed_validation, context_source)

            case ManagedExpressionsEnum.BETWEEN:
                managed_validation = cast(Between, managed_validation)
                _configure_between_expression(self, managed_validation, context_source)

            case ManagedExpressionsEnum.BETWEEN_DATES:
                managed_validation = cast(BetweenDates, managed_validation)
                _configure_between_dates_expression(self, managed_validation, presentation_options, context_source)

    def click_managed_validation_type(self, managed_validation: ManagedExpression) -> None:
        self.page.get_by_role("radio", name=managed_validation._key.value).click()

    def click_insert_data(self, field_name: str) -> "SelectDataSourcePage":
        self.page.get_by_role("button", name=f"Reference data for {field_name}").click()
        return SelectDataSourcePage(page=self.page, domain=self.domain, grant_name=self.grant_name)

    def click_add_validation(self) -> "EditQuestionPage":
        self.add_validation_button.click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class AddConditionPage(ReportsBasePage):
    add_condition_button: Locator
    continue_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add a condition"),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.add_condition_button = self.page.get_by_role("button", name="Add condition")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def configure_managed_condition(
        self,
        managed_condition: ManagedExpression,
        context_source: DataReferenceConfig | None = None,
        presentation_options: QuestionPresentationOptions | None = None,
    ) -> None:
        self.click_managed_condition_type(managed_condition)

        match managed_condition._key:
            case ManagedExpressionsEnum.GREATER_THAN:
                managed_condition = cast(GreaterThan, managed_condition)
                _configure_greater_than_expression(self, managed_condition, context_source)

            case ManagedExpressionsEnum.LESS_THAN:
                managed_condition = cast(LessThan, managed_condition)
                _configure_less_than_expression(self, managed_condition, context_source)

            case ManagedExpressionsEnum.BETWEEN:
                managed_condition = cast(Between, managed_condition)
                _configure_between_expression(self, managed_condition, context_source)

            case ManagedExpressionsEnum.BETWEEN_DATES:
                managed_condition = cast(BetweenDates, managed_condition)
                _configure_between_dates_expression(self, managed_condition, presentation_options, context_source)

            case ManagedExpressionsEnum.IS_YES | ManagedExpressionsEnum.IS_NO:
                return

            case ManagedExpressionsEnum.ANY_OF:
                managed_condition = cast(AnyOf, managed_condition)
                for item in managed_condition.items:
                    self.page.get_by_role("checkbox", name=item["label"]).click()

            case ManagedExpressionsEnum.SPECIFICALLY:
                managed_condition = cast(Specifically, managed_condition)
                self.page.get_by_role("radio", name=managed_condition.item["label"]).click()

    def click_managed_condition_type(self, managed_condition: ManagedExpression) -> None:
        self.page.get_by_role("radio", name=managed_condition._key.value).click()

    def click_insert_data(self, field_name: str) -> "SelectDataSourcePage":
        self.page.get_by_role("button", name=f"Reference data for {field_name}").click()
        return SelectDataSourcePage(page=self.page, domain=self.domain, grant_name=self.grant_name)

    def select_condition_question(self, condition_config: DataReferenceConfig) -> None:
        # We don't easily know randomly generated uuid apended to the previous question texts, so have to grab it to
        # select the correct option
        expect(self.page.locator("[class='autocomplete__wrapper']")).to_be_attached()
        element = self.page.get_by_role("combobox")
        element.click()
        assert condition_config.question_text
        element.fill(condition_config.question_text)
        element.press("Enter")

        self.continue_button.click()

    def click_add_condition(
        self, edit_page: EditQuestionPage | EditQuestionGroupPage
    ) -> EditQuestionPage | EditQuestionGroupPage:
        self.add_condition_button.click()

        if isinstance(edit_page, EditQuestionGroupPage):
            edit_page = EditQuestionGroupPage(
                self.page,
                self.domain,
                grant_name=self.grant_name,
                report_name=self.report_name,
                section_name=self.section_name,
                group_name=edit_page.group_name,
            )
        else:
            edit_page = EditQuestionPage(
                self.page,
                self.domain,
                grant_name=self.grant_name,
                report_name=self.report_name,
                section_name=self.section_name,
            )

        expect(edit_page.heading).to_be_visible()
        return edit_page


class SelectQuestionTypePage(ReportsBasePage):
    report_name: str
    section_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What type of question do you need?"),
        )
        self.report_name = report_name
        self.section_name = section_name

    def click_question_type(self, question_type: str) -> None:
        self.page.get_by_role("radio", name=question_type).click()

    def click_continue(self) -> AddQuestionDetailsPage:
        self.page.get_by_role("button", name="Continue").click()
        question_details_page = AddQuestionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(question_details_page.heading).to_be_visible()
        return question_details_page


class AddQuestionDetailsPage(ReportsBasePage):
    report_name: str
    section_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add question"),
        )
        self.report_name = report_name
        self.section_name = section_name

    def fill_question_text(self, question_text: str) -> None:
        self.page.get_by_role("textbox", name="Question text").fill(question_text)

    def fill_question_name(self, question_name: str) -> None:
        self.page.get_by_role("textbox", name="Question name").fill(question_name)

    def fill_question_hint(self, question_hint: str) -> None:
        self.page.get_by_role("textbox", name="Question hint").fill(question_hint)

    def click_insert_data(self, field_name: Literal["text", "hint"], question: str) -> "SelectDataSourcePage":
        self.page.get_by_role("button", name=f"Reference data in question {field_name}").click()

        return SelectDataSourcePage(page=self.page, domain=self.domain, grant_name=self.grant_name)

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

    def click_is_approximate_date_checkbox(self) -> None:
        self.page.get_by_role("checkbox", name="Ask for an approximate date (month and year only)").click()

    def click_submit(self) -> "EditQuestionPage":
        self.page.get_by_role("button", name="Add question").click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class SelectDataSourcePage(ReportsBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page=page,
            domain=domain,
            heading=page.get_by_role("heading", name="Select data source"),
            grant_name=grant_name,
        )

    def select_data_source(
        self, data_source: ExpressionContext.ContextSources
    ) -> SelectDataSourceQuestionPage | SelectDataSourceSectionPage:
        self.page.get_by_role("radio", name=data_source.value).click()
        self.page.get_by_role("button", name="Select data source").click()

        match data_source:
            case ExpressionContext.ContextSources.SECTION:
                return SelectDataSourceQuestionPage(page=self.page, domain=self.domain, grant_name=self.grant_name)

            case ExpressionContext.ContextSources.PREVIOUS_SECTION:
                return SelectDataSourceSectionPage(page=self.page, domain=self.domain, grant_name=self.grant_name)

            case ExpressionContext.ContextSources.PREVIOUS_COLLECTION:
                pass

        raise NotImplementedError(f"Unexpected data source: {data_source}")


class SelectDataSourceSectionPage(ReportsBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page=page,
            domain=domain,
            heading=page.get_by_role("heading", name="Select a previous section"),
            grant_name=grant_name,
        )

    def choose_section(self, section_name: str) -> SelectDataSourceQuestionPage:
        self.page.get_by_role("radio", name=section_name).click()
        self.page.get_by_role("button", name="Select section").click()
        return SelectDataSourceQuestionPage(page=self.page, domain=self.domain, grant_name=self.grant_name)


class SelectDataSourceQuestionPage(ReportsBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page=page,
            domain=domain,
            heading=page.get_by_role("heading", name="Select data source"),
            grant_name=grant_name,
        )

    def choose_question(self, question: str) -> None:
        # there is a few ms of delay during the call to "enhanceSelectElement" which allows the select
        # being progressively enhanced to be selected before its complete as playwright will act immediately
        # on the role being available - this causes the test to fail particularly when there is network latency.
        # Wait for the full input + options to be loaded before using it
        expect(self.page.locator("[class='autocomplete__wrapper']")).to_be_attached()
        element = self.page.get_by_role("combobox")
        element.click()
        element.fill(question)
        element.press("Enter")

    def click_use_data(self) -> None:
        self.page.get_by_role("button", name="Reference data").click()


class AddSectionPage(ReportsBasePage):
    report_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the section?"),
        )
        self.report_name = report_name

    def fill_in_section_name(self, section_name: str) -> None:
        self.page.get_by_role("textbox", name="Section name").fill(section_name)

    def click_add_section(self) -> ReportSectionsPage:
        self.page.get_by_role("button", name="Add section").click()
        report_sections_page = ReportSectionsPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(report_sections_page.heading).to_be_visible()
        return report_sections_page


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

    def click_on_section(self, section_name: str) -> None:
        self.page.get_by_role("link", name=section_name).click()

    def click_submit_for_preview(self) -> ReportSectionsPage:
        self.submit_button.click()
        report_sections_page = ReportSectionsPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(report_sections_page.heading).to_be_visible()
        return report_sections_page

    def click_submit_for_certify(self) -> None:
        self.submit_button.click()
        expect(self.page.get_by_text("Report submitted to certifier")).to_be_visible()

    def click_back(self) -> ReportSectionsPage:
        self.back_link.click()
        report_sections_page = ReportSectionsPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(report_sections_page.heading).to_be_visible()
        return report_sections_page


class RunnerQuestionPage(ReportsBasePage):
    continue_button: Locator
    question_name: str

    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
        question_name: str,
        is_in_a_same_page_group: bool = False,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_text(question_name, exact=True)
            if is_in_a_same_page_group
            else page.get_by_role("heading", name=question_name),
        )
        self.question_name = question_name
        self.continue_button = page.get_by_role("button", name="Continue")

    def respond_to_question(self, question_type: QuestionDataType, question_text: str, answer: str) -> None:
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
        elif question_type == QuestionDataType.DATE:
            approx_date = len(answer) == 2
            date_to_enter = (
                datetime.date(*[int(a) for a in answer])
                if not approx_date
                else datetime.date(int(answer[0]), int(answer[1]), 1)
            )
            ReportsBasePage.fill_in_date_fields(
                self.page.get_by_role("group", name=question_text),
                date_to_enter,
                approx_date=approx_date,
            )
        else:
            self.page.get_by_role("textbox", name=question_text).fill(answer)

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
        self.mark_as_complete_yes = page.get_by_role("radio", name="Yes, I’ve completed this section")

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

    def click_on_submission(self, submission_reference: str) -> ViewSubmissionPage:
        self.page.get_by_role("link", name=submission_reference).click()
        view_submission_page = ViewSubmissionPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(view_submission_page.heading).to_be_visible()
        return view_submission_page

    def click_export(self, filetype: str) -> str:
        with self.page.expect_download() as download_info:
            self.page.get_by_role("button", name=f"Export as {filetype}").click()
        download = download_info.value
        tempdir = tempfile.gettempdir()
        download_filename = tempdir + "/" + download_info.value.suggested_filename
        download.save_as(download_filename)

        return download_filename


class ViewSubmissionPage(ReportsBasePage):
    report_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Submission", exact=True),
        )
        self.report_name = report_name

    def get_questions_list_for_section(self, section_name: str) -> Locator:
        return self.page.get_by_test_id(section_name)

    def click_submissions_breadcrumb(self) -> SubmissionsListPage:
        self.page.locator("a.govuk-breadcrumbs__link").filter(has=self.page.get_by_text("Submissions")).click()
        submissions_list_page = SubmissionsListPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(submissions_list_page.heading).to_be_visible()
        return submissions_list_page

    def click_reset_submission(self) -> SubmissionsListPage:
        self.page.get_by_role("link", name="Reset this submission").click()
        self.page.get_by_role("button", name="Yes, reset this test submission").click()
        expect(self.page.get_by_text("Test submission reset")).to_be_visible()
        submissions_list_page = SubmissionsListPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(submissions_list_page.heading).to_be_visible()
        return submissions_list_page


class AddQuestionGroupPage(ReportsBasePage):
    def __init__(
        self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str, group_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the question group?"),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.group_name = group_name

    def fill_in_question_group_name(self) -> None:
        self.page.get_by_role("textbox", name="Question group name").fill(self.group_name)

    def click_continue(self) -> AddQuestionGroupDisplayOptionsPage:
        self.page.get_by_role("button", name="Continue").click()
        question_group_display_options_page = AddQuestionGroupDisplayOptionsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=self.group_name,
        )
        expect(question_group_display_options_page.heading).to_be_visible()
        return question_group_display_options_page


class AddQuestionGroupDisplayOptionsPage(ReportsBasePage):
    def __init__(
        self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str, group_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="How should the question group be displayed?"),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.group_name = group_name

    def click_question_group_display_type(self, display_options: GroupDisplayOptions) -> None:
        match display_options:
            case GroupDisplayOptions.ONE_QUESTION_PER_PAGE:
                self.page.get_by_role("radio", name="One question per page").click()

            case GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE:
                self.page.get_by_role("radio", name="All questions on the same page").click()

            case _:
                raise ValueError("Unknown group display option: {_}")

    def click_submit(self) -> AddQuestionGroupAddAnotherPage:
        self.page.get_by_role("button", name="Continue").click()
        group_add_another_page = AddQuestionGroupAddAnotherPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=self.group_name,
        )
        expect(group_add_another_page.heading).to_be_visible()
        return group_add_another_page


class AddQuestionGroupAddAnotherPage(ReportsBasePage):
    def __init__(
        self, page: Page, domain: str, grant_name: str, report_name: str, section_name: str, group_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role(
                "heading", name="Should people be able to answer all questions in this question group more than once?"
            ),
        )
        self.report_name = report_name
        self.section_name = section_name
        self.group_name = group_name

    def click_add_another(self, add_another: bool) -> None:
        if add_another:
            self.page.get_by_role("radio", name="yes").click()
        else:
            self.page.get_by_role("radio", name="no").click()

    def click_submit(self, parent_group_name: str | None = None) -> EditQuestionGroupPage:
        self.page.get_by_role("button", name="Add question group").click()
        edit_group_page = EditQuestionGroupPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=self.group_name,
            parent_group_name=parent_group_name,
        )
        expect(edit_group_page.heading).to_be_visible()
        return edit_group_page


class EditQuestionGroupPage(ReportsBasePage):
    section_breadcrumb: Locator
    parent_breadcrumb: Locator | None
    change_display_options_link: Locator
    add_question_button: Locator
    add_guidance_button: Locator
    add_condition_button: Locator
    change_guidance_link: Locator
    add_question_group_button: Locator

    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
        report_name: str,
        section_name: str,
        group_name: str,
        parent_group_name: str | None = None,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=group_name),
        )
        self.parent_group_name = parent_group_name
        self.report_name = report_name
        self.section_name = section_name
        self.group_name = group_name
        self.section_breadcrumb = self.page.locator("a.govuk-breadcrumbs__link").filter(
            has=page.get_by_text(f"{section_name}")
        )
        self.parent_breadcrumb = self.page.get_by_role("link", name=parent_group_name) if parent_group_name else None

        self.add_question_button = self.page.get_by_role("link", name="Add a question", exact=True).or_(
            self.page.get_by_role("link", name="Add another question")
        )
        self.add_condition_button = self.page.get_by_role("button", name="Add condition")
        self.add_guidance_button = self.page.get_by_role("link", name="Add guidance")
        self.change_display_options_link = self.page.get_by_role("link", name="Change")
        self.change_guidance_link = self.page.get_by_role("link", name="Change  page heading")
        self.add_question_group_button = self.page.get_by_role("link", name="Add a question group", exact=True)

    def click_section_breadcrumb(self) -> ManageSectionPage:
        self.section_breadcrumb.click()
        manage_section_page = ManageSectionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(manage_section_page.heading).to_be_visible()
        return manage_section_page

    def click_parent_group_breadcrumb(self) -> EditQuestionGroupPage:
        assert self.parent_breadcrumb
        self.parent_breadcrumb.click()
        manage_parent_group_page = EditQuestionGroupPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=self.parent_group_name,  # type: ignore[arg-type]
        )
        expect(manage_parent_group_page.heading).to_be_visible()
        return manage_parent_group_page

    def click_add_question_group(self, group_name: str) -> AddQuestionGroupPage:
        self.add_question_group_button.click()

        add_question_group_page = AddQuestionGroupPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=group_name,
        )
        expect(add_question_group_page.heading).to_be_visible()
        return add_question_group_page

    def click_add_question(self) -> SelectQuestionTypePage:
        self.add_question_button.click()

        select_question_type_page = SelectQuestionTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(select_question_type_page.heading).to_be_visible()
        return select_question_type_page

    def click_add_condition(self) -> AddConditionPage:
        self.add_condition_button.click()
        add_condition_page = AddConditionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(add_condition_page.heading).to_be_visible()
        return add_condition_page

    def click_add_guidance(self) -> AddGuidancePage:
        self.add_guidance_button.click()
        add_guidance_page = AddGuidancePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(add_guidance_page.heading).to_be_visible()
        return add_guidance_page

    def click_change_display_options(self) -> AddQuestionGroupDisplayOptionsPage:
        self.change_display_options_link.click()
        question_group_display_options_page = AddQuestionGroupDisplayOptionsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
            group_name=self.group_name,
        )
        expect(question_group_display_options_page.heading).to_be_visible()
        return question_group_display_options_page

    def click_change_guidance(self) -> AddGuidancePage:
        self.change_guidance_link.click()
        add_guidance_page = AddGuidancePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            section_name=self.section_name,
        )
        expect(add_guidance_page.heading).to_be_visible()
        return add_guidance_page


class AdminReportingLifecycleTasklistPage:
    def __init__(self, page: Page, domain: str, grant_id: str, collection_id: str) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id

    def navigate(self) -> None:
        self.page.goto(
            url=f"{self.domain}/deliver/admin/reporting-lifecycle/{str(self.grant_id)}/{str(self.collection_id)}"
        )

    def click_task(self, task_name: str) -> None:
        self.page.get_by_role("link", name=re.compile(task_name)).click()


class SetUpOrganisationsPage:
    def __init__(
        self, page: Page, domain: str, grant_id: str, collection_id: str, heading: Locator | None = None
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = heading or page.get_by_role("heading", name="Set up organisations")
        self.organisations_textarea = page.locator("textarea[name='organisations_data']")
        self.set_up_button = page.get_by_role("button", name="Set up organisations")

    def navigate(self) -> None:
        self.page.goto(
            f"{self.domain}/deliver/admin/reporting-lifecycle/{self.grant_id}/{self.collection_id}/set-up-organisations"
        )
        expect(self.heading).to_be_visible()

    def fill_organisations_tsv_data(self, tsv_data: str) -> None:
        self.organisations_textarea.fill(tsv_data)

    def click_set_up_organisations(self) -> "AdminReportingLifecycleTasklistPage":
        self.set_up_button.click()
        expect(self.page.get_by_text("Created or updated 1 organisation")).to_be_visible()
        return AdminReportingLifecycleTasklistPage(self.page, self.domain, self.grant_id, self.collection_id)


class SetUpTestOrganisationsPage(SetUpOrganisationsPage):
    def __init__(self, page: Page, domain: str, grant_id: str, collection_id: str) -> None:
        super().__init__(
            page=page,
            domain=domain,
            grant_id=grant_id,
            collection_id=collection_id,
            heading=page.get_by_role("heading", name="Set up test organisations"),
        )

    def navigate(self) -> None:
        self.page.goto(
            f"{self.domain}/deliver/admin/reporting-lifecycle/{self.grant_id}/{self.collection_id}/set-up-test-organisations"
        )
        expect(self.heading).to_be_visible()

    def click_set_up_organisations(self) -> "AdminReportingLifecycleTasklistPage":
        self.set_up_button.click()
        expect(self.page.get_by_text("Created or updated 1 test organisation")).to_be_visible()
        return AdminReportingLifecycleTasklistPage(self.page, self.domain, self.grant_id, self.collection_id)


class SetUpGrantRecipientsPage:
    def __init__(
        self, page: Page, domain: str, grant_id: str, collection_id: str, heading: Locator | None = None
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = heading or page.get_by_role("heading", name="Set up grant recipients")

        self.grant_recipients_combobox = page.locator(".choices", has=page.locator(".choices__input#recipients"))
        expect(self.grant_recipients_combobox).to_be_visible()

        self.set_up_button = page.get_by_role("button", name="Set up grant recipients")

    def select_organisation(self, org_name: str) -> None:
        self.grant_recipients_combobox.click()
        self.page.get_by_role("option", name=org_name).click()
        self.page.keyboard.press("Escape")

    def click_set_up_grant_recipients(self) -> "AdminReportingLifecycleTasklistPage":
        self.set_up_button.click()
        expect(self.page.get_by_text("Created 1 grant recipient")).to_be_visible()
        return AdminReportingLifecycleTasklistPage(self.page, self.domain, self.grant_id, self.collection_id)


class SetUpTestGrantRecipientsPage(SetUpGrantRecipientsPage):
    def __init__(self, page: Page, domain: str, grant_id: str, collection_id: str) -> None:
        super().__init__(
            page, domain, grant_id, collection_id, page.get_by_role("heading", name="Set up test grant recipients")
        )

    def click_set_up_grant_recipients(self) -> "AdminReportingLifecycleTasklistPage":
        self.set_up_button.click()
        expect(self.page.get_by_text("Created 1 test grant recipient")).to_be_visible()
        return AdminReportingLifecycleTasklistPage(self.page, self.domain, self.grant_id, self.collection_id)


class SetUpTestGrantRecipientUsersPage:
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_id: str,
        collection_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = page.get_by_role("heading", name="Add users to test Access grant funding")

        self.test_grant_recipient_combobox = page.locator(
            ".choices", has=page.locator(".choices__input#grant_recipient")
        )
        expect(self.test_grant_recipient_combobox).to_be_visible()

        self.grant_team_members_combobox = page.locator(".choices", has=page.locator(".choices__input#user"))
        expect(self.grant_team_members_combobox).to_be_visible()

        self.add_user_button = page.get_by_role("button", name="Add user")

    def select_test_grant_recipient(self, org_name: str) -> None:
        self.test_grant_recipient_combobox.click()
        self.page.get_by_role("option", name=org_name).click()

    def select_grant_team_member(self, email_pattern: str) -> None:
        self.grant_team_members_combobox.click()
        self.page.get_by_role("option", name=re.compile(email_pattern)).click()

    def click_add_user(self) -> None:
        self.add_user_button.click()
        expect(self.page.get_by_text("Added")).to_be_visible()


class SetUpDataProvidersPage:
    def __init__(
        self, page: Page, domain: str, grant_id: str, collection_id: str, heading: Locator | None = None
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = heading or page.get_by_role("heading", name="Set up grant recipient data providers")
        self.users_textarea = page.locator("textarea[name='users_data']")
        self.set_up_button = page.get_by_role("button", name="Set up data providers")

    def navigate(self) -> None:
        self.page.goto(
            f"{self.domain}/deliver/admin/reporting-lifecycle/{self.grant_id}/{self.collection_id}/add-bulk-data-providers"
        )
        expect(self.heading).to_be_visible()

    def fill_users_tsv_data(self, tsv_data: str) -> None:
        self.users_textarea.fill(tsv_data)

    def click_set_up_users(self) -> "AdminReportingLifecycleTasklistPage":
        self.set_up_button.click()
        expect(self.page.get_by_text("Successfully set up 1 grant recipient data provider.")).to_be_visible()
        return AdminReportingLifecycleTasklistPage(self.page, self.domain, self.grant_id, self.collection_id)


class OverrideGrantRecipientCertifiersPage:
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_id: str,
        collection_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = page.get_by_role("heading", name="Override certifiers for this grant")

        self.organisation_combo_box = page.locator(".choices", has=page.locator(".choices__input#organisation_id"))

        self.user_full_name_box = page.get_by_role("textbox", name="Full name")
        self.user_email_box = page.get_by_role("textbox", name="Email address")

        self.add_certifer_button = page.get_by_role("button", name="Add grant-specific certifier")

    def select_organisation(self, org_name: str) -> None:
        self.organisation_combo_box.click()
        self.page.get_by_role("option", name=org_name).click()

    def complete_user_details(self, full_name: str, email: str) -> None:
        self.user_full_name_box.fill(full_name)
        self.user_email_box.fill(email)

    def click_add_certifier(self) -> None:
        self.add_certifer_button.click()
        expect(self.page.get_by_text("Successfully added ")).to_be_visible()


class SetReportingDatesPage:
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_id: str,
        collection_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = page.get_by_role("heading", name="Set reporting and submission dates")
        self.save_dates_button = page.get_by_role("button", name="Save dates")

    def complete_reporting_start_date(self, start_date: datetime.date) -> None:
        ReportsBasePage.fill_in_date_fields(
            self.page.get_by_role("group", name="Reporting period start date"),
            start_date,
        )

    def complete_reporting_end_date(self, start_date: datetime.date) -> None:
        ReportsBasePage.fill_in_date_fields(
            self.page.get_by_role("group", name="Reporting period end date"),
            start_date,
        )

    def complete_submission_start_date(self, start_date: datetime.date) -> None:
        ReportsBasePage.fill_in_date_fields(
            self.page.get_by_role("group", name="Submission period start date"),
            start_date,
        )

    def complete_submission_end_date(self, start_date: datetime.date) -> None:
        ReportsBasePage.fill_in_date_fields(
            self.page.get_by_role("group", name="Submission period end date"),
            start_date,
        )

    def click_save_dates(self, report_name: str) -> None:
        self.save_dates_button.click()
        expect(self.page.get_by_text(f"Updated dates for {report_name}.")).to_be_visible()

    def set_dates_for_open_report(self) -> None:
        now = datetime.datetime.now()
        self.complete_reporting_start_date(now - datetime.timedelta(weeks=12))
        self.complete_reporting_end_date(now - datetime.timedelta(weeks=8))
        self.complete_submission_start_date(now - datetime.timedelta(days=15))
        self.complete_submission_end_date(now + datetime.timedelta(days=15))


class MarkAsOnboardingWithFundingServicePage:
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_id: str,
        collection_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = page.get_by_role("heading", name="Mark grant as onboarding with Funding Service")
        self.mark_as_onboarding_button = page.get_by_role("button", name="Mark as onboarding")

    def click_mark_as_onboarding(self) -> None:
        self.mark_as_onboarding_button.click()
        expect(self.page.get_by_text("is now marked as onboarding.")).to_be_visible()


class SetPrivacyPolicyPage:
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_id: str,
        collection_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.collection_id = collection_id
        self.heading = page.get_by_role("heading", name="Set privacy policy")
        self.save_button = page.get_by_role("button", name="Save privacy policy")

    def fill_privacy_policy_markdown(self, privacy_policy: str) -> None:
        self.page.get_by_role("textbox", name="Privacy policy markdown").fill(privacy_policy)

    def click_save_privacy_policy(self) -> None:
        self.save_button.click()
        expect(self.page.get_by_text("Privacy policy updated for ")).to_be_visible()


class PlatformAdminGrantSettingsPage:
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.grant_id = grant_id
        self.heading = page.get_by_role("heading", name="Edit Grant")
        self.status_dropdown = page.get_by_role("combobox", name="Status")
        self.save_button = page.get_by_role("button", name="Save")

    def navigate(self) -> None:
        self.page.goto(url=f"{self.domain}/deliver/admin/grant/edit/?id={self.grant_id}")
        expect(self.heading).to_be_visible()

    def select_grant_status(self, status: str) -> None:
        self.status_dropdown.select_option(status)

    def click_save(self) -> None:
        self.save_button.click()
        expect(self.page.get_by_text("Record was successfully saved.")).to_be_visible()


class PlatformAdminReportSettingsPage:
    def __init__(
        self,
        page: Page,
        domain: str,
        collection_id: str,
    ) -> None:
        self.page = page
        self.domain = domain
        self.collection_id = collection_id
        self.heading = page.get_by_role("heading", name="Edit Collection")
        self.status_dropdown = page.get_by_role("combobox", name="Status")
        self.save_button = page.get_by_role("button", name="Save")

    def navigate(self) -> None:
        self.page.goto(url=f"{self.domain}/deliver/admin/collection/edit/?id={self.collection_id}")
        expect(self.heading).to_be_visible()

    def select_collection_status(self, status: str) -> None:
        self.status_dropdown.select_option(status)

    def click_save(self) -> None:
        self.save_button.click()
        expect(self.page.get_by_text("Record was successfully saved.")).to_be_visible()
