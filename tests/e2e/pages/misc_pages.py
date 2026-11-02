import datetime
from typing import TYPE_CHECKING

from playwright.sync_api import Locator, Page, expect

from app.common.data.types import QuestionDataType

if TYPE_CHECKING:
    from tests.e2e.pages.deliver_pages import GrantTeamPage, ReportSectionsPage, SSOSignInPage


class BasePage:
    domain: str
    page: Page

    def __init__(self, page: Page, domain: str) -> None:
        self.page = page
        self.domain = domain


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
        from tests.e2e.pages.deliver_pages import SSOSignInPage

        self.page.get_by_role("link", name="Sign out").click()
        sso_sign_in_page = SSOSignInPage(self.page, self.domain)
        return sso_sign_in_page

    def click_nav_grant_team(self) -> GrantTeamPage:
        from tests.e2e.pages.deliver_pages import GrantTeamPage

        self.page.get_by_role("link", name="Team").click()
        sso_sign_in_page = GrantTeamPage(self.page, self.domain)
        return sso_sign_in_page


class RunnerTasklistPage(ReportsBasePage):
    report_name: str
    submission_status_box: Locator
    submit_button: Locator
    back_link: Locator
    status_tags: Locator

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
        self.status_tags = page.locator(".govuk-tag")

    def status_tag_with_text(self, text: str) -> Locator:
        return self.status_tags.filter(has_text=text)

    def click_on_section(self, section_name: str) -> None:
        self.page.get_by_role("link", name=section_name).click()

    def click_submit_for_preview(self) -> ReportSectionsPage:
        from tests.e2e.pages.deliver_pages import ReportSectionsPage

        self.submit_button.click()
        report_sections_page = ReportSectionsPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(report_sections_page.heading).to_be_visible()
        return report_sections_page

    def click_submit_for_certify(self) -> ReportSubmittedConfirmationPage:
        self.submit_button.click()
        submitted_page = ReportSubmittedConfirmationPage(
            page=self.page,
            domain=self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            submitted_to_certifier=True,
        )
        expect(submitted_page.heading).to_be_visible()
        return submitted_page

    def click_submit_for_direct_submission(self) -> PreAwardConfirmSubmitPage:
        self.submit_button.click()
        confirm_submit_page = PreAwardConfirmSubmitPage(self.page, self.domain, self.grant_name)
        expect(confirm_submit_page.heading).to_be_visible()
        return confirm_submit_page

    def click_back(self) -> ReportSectionsPage:
        from tests.e2e.pages.deliver_pages import ReportSectionsPage

        self.back_link.click()
        report_sections_page = ReportSectionsPage(
            self.page, self.domain, grant_name=self.grant_name, report_name=self.report_name
        )
        expect(report_sections_page.heading).to_be_visible()
        return report_sections_page


class ReportSubmittedConfirmationPage(ReportsBasePage):
    report_name: str
    return_to_reports_link: Locator

    def __init__(
        self, page: Page, domain: str, grant_name: str, report_name: str, submitted_to_certifier: bool
    ) -> None:
        super().__init__(
            page=page,
            domain=domain,
            grant_name=grant_name,
            heading=page.get_by_role(
                "heading",
                name=("Report submitted to certifier" if submitted_to_certifier else "Report signed off and submitted"),
            ),
        )
        self.report_name = report_name
        self.return_to_reports_link = page.get_by_role("link", name="Return to reports")

    def click_return_to_reports(self) -> None:
        self.return_to_reports_link.click()


class PreAwardConfirmSubmitPage(ReportsBasePage):
    confirm_submit_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Confirm and submit form"),
        )
        self.confirm_submit_button = page.get_by_role("button", name="Confirm and submit")

    def click_confirm_and_submit(self) -> PreAwardFormSubmittedConfirmationPage:
        self.confirm_submit_button.click()
        confirmation_page = PreAwardFormSubmittedConfirmationPage(self.page, self.domain, self.grant_name)
        expect(confirmation_page.heading).to_be_visible()
        return confirmation_page


class PreAwardFormSubmittedConfirmationPage(ReportsBasePage):
    return_to_forms_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Form submitted"),
        )
        self.return_to_forms_link = page.get_by_role("link", name="Return to forms")

    def click_return_to_forms(self) -> None:
        self.return_to_forms_link.click()


class ViewLockedReportPage(ReportsBasePage):
    report_name: str
    sign_off_and_submit_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            domain=domain,
            page=page,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"Review report: {report_name}"),
        )
        self.report_name = report_name
        self.sign_off_and_submit_button = page.get_by_role("button", name="Continue to sign off and submit")

    def click_sign_off_and_submit(self) -> ConfirmSignOffPage:
        self.sign_off_and_submit_button.click()
        sign_off_page = ConfirmSignOffPage(self.page, self.domain, self.grant_name, self.report_name)
        expect(sign_off_page.heading).to_be_visible()
        return sign_off_page


class ConfirmSignOffPage(ReportsBasePage):
    report_name: str
    sign_off_and_submit_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, report_name: str) -> None:
        super().__init__(
            page=page,
            domain=domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Confirm sign off and submit report"),
        )
        self.report_name = report_name
        self.sign_off_and_submit_button = page.get_by_role("button", name="Confirm sign off and submit")

    def click_sign_off_and_submit(self) -> ReportSubmittedConfirmationPage:
        self.sign_off_and_submit_button.click()
        confirmation_page = ReportSubmittedConfirmationPage(
            page=self.page,
            domain=self.domain,
            grant_name=self.grant_name,
            report_name=self.report_name,
            submitted_to_certifier=False,
        )
        expect(confirmation_page.heading).to_be_visible()
        return confirmation_page


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

    def respond_to_question(self, question_type: QuestionDataType, question_text: str, answer: str | list[str]) -> None:
        if isinstance(answer, list):
            if question_type == QuestionDataType.CHECKBOXES:
                for choice in answer:
                    self.page.get_by_role("checkbox", name=choice).click()
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
                raise ValueError(f"respond_to_question got a list of answers, but question type was {question_type}")
        else:
            if question_type in [QuestionDataType.YES_NO, QuestionDataType.RADIOS]:
                # once we start having multiple of these on a page - enjoy the refactor =]
                accessible_autocomplete = self.page.query_selector("[data-accessible-autocomplete]")
                if accessible_autocomplete:
                    # there is a few ms of delay during the call to "enhanceSelectElement" which allows the select
                    # being progressively enhanced to be selected before its complete as playwright will act immediately
                    # on the role being available - this causes the test to fail particularly when there is network
                    # latency.
                    # Wait for the full input + options to be loaded before using it
                    expect(self.page.locator("[class='autocomplete__wrapper']")).to_be_attached()
                    element = self.page.get_by_role("combobox")
                    element.click()
                    element.fill(answer)
                    element.press("Enter")
                else:
                    self.page.get_by_role("radio", name=answer).click()

            elif question_type == QuestionDataType.FILE_UPLOAD:
                self.page.locator("input[type='file']").set_input_files("./tests/fixtures/e2e-test-file.txt")
            else:
                self.page.get_by_role("textbox", name=question_text).fill(answer)

    def click_continue(
        self,
    ) -> None:
        self.continue_button.click()


class RunnerCheckYourAnswersPage(ReportsBasePage):
    save_and_continue_button: Locator
    mark_as_complete_yes: Locator
    changes_requested_reason_inset: Locator

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
        self.changes_requested_reason_inset = page.locator(".govuk-inset-text")

    def click_mark_as_complete_yes(self) -> None:
        self.mark_as_complete_yes.click()

    def click_change_answer(self, question_name: str) -> RunnerQuestionPage:
        self.page.get_by_role("link", name=f"Change {question_name}").click()
        question_page = RunnerQuestionPage(self.page, self.domain, self.grant_name, question_name)
        expect(question_page.heading).to_be_visible()
        return question_page

    def click_save_and_continue(self, report_name: str) -> RunnerTasklistPage:
        self.save_and_continue_button.click()
        task_list_page = RunnerTasklistPage(self.page, self.domain, self.grant_name, report_name=report_name)
        expect(task_list_page.heading).to_be_visible()
        return task_list_page


class RunnerAddAnotherSummaryPage(ReportsBasePage):
    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
        group_name: str,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=group_name, exact=True),
        )
        self.group_name = group_name

    def expect_empty(self) -> None:
        expect(self.heading).to_be_visible()
        expect(self.page.get_by_text(f"You have not added any {self.group_name}.")).to_be_visible()

    def expect_count(self, count: int) -> None:
        expect(self.heading).to_be_visible()
        expect(self.page.get_by_text(f"You have added {count} {self.group_name}")).to_be_visible()

    def click_add_first_answer(self) -> None:
        self.page.get_by_role("button", name="Add the first answer").click()

    def click_add_another_yes(self) -> None:
        self.page.get_by_role("radio", name="Yes").click()
        self.page.get_by_role("button", name="Continue").click()

    def click_add_another_no(self) -> None:
        self.page.get_by_role("radio", name="No").click()
        self.page.get_by_role("button", name="Continue").click()

    def click_change(self, index: int = 0) -> None:
        self.page.get_by_role("link", name="Change", exact=False).nth(index).click()

    def click_remove_first(self) -> None:
        self.page.get_by_role("link", name="Remove", exact=False).first.click()

    def click_remove_last(self) -> None:
        self.page.get_by_role("link", name="Remove", exact=False).last.click()


class RunnerAddAnotherRemovePage(ReportsBasePage):
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
            heading=page.get_by_role("heading", name="Are you sure you want to remove", exact=False),
        )

    def confirm_remove(self) -> None:
        expect(self.heading).to_be_visible()
        self.page.get_by_role("radio", name="Yes").click()
        self.page.get_by_role("button", name="Continue").click()

    def cancel_remove(self) -> None:
        expect(self.heading).to_be_visible()
        self.page.get_by_role("radio", name="No").click()
        self.page.get_by_role("button", name="Continue").click()
