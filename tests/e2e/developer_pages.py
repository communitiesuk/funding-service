from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from playwright.sync_api import Locator, Page, expect

from app.common.data.types import ManagedExpressionsEnum, QuestionDataType
from app.common.expressions.managed import GreaterThan, LessThan, ManagedExpression
from app.constants import DEFAULT_SECTION_NAME

if TYPE_CHECKING:
    from tests.e2e.pages import AllGrantsPage


class GrantDevelopersBasePage:
    domain: str
    page: Page

    heading: Locator
    grant_name: str

    def __init__(self, page: Page, domain: str, heading: Locator, grant_name: str) -> None:
        self.page = page
        self.domain = domain
        self.heading = heading
        self.grant_name = grant_name


class GrantDevelopersPage(GrantDevelopersBasePage):
    manage_collections_link: Locator
    delete_link: Locator
    confirm_delete: Locator
    add_collection_button: Locator
    summary_row_submissions: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} Developers")
        )
        self.manage_collections_link = self.page.get_by_role("link", name="Manage")
        self.delete_link = page.get_by_role("link", name="Delete this grant")
        self.confirm_delete = page.get_by_role("button", name="Confirm deletion")
        self.add_collection_button = self.page.get_by_role("button", name="Add a monitoring report").or_(
            self.page.get_by_role("button", name="Add another monitoring report")
        )
        self.summary_row_submissions = page.locator("div.govuk-summary-list__row").filter(
            has=page.get_by_text("Submissions")
        )

    def delete_grant(self) -> "AllGrantsPage":
        from tests.e2e.pages import AllGrantsPage

        self.delete_link.click()
        self.confirm_delete.click()
        all_grants_page = AllGrantsPage(self.page, self.domain)
        expect(all_grants_page.title).to_be_visible()
        return all_grants_page

    def click_add_collection(self) -> AddCollectionPage:
        self.add_collection_button.click()
        add_collection_page = AddCollectionPage(self.page, self.domain, grant_name=self.grant_name)
        expect(add_collection_page.heading).to_be_visible()
        return add_collection_page

    def check_collection_exists(self, collection_name: str) -> None:
        expect(self.page.get_by_role("heading", name=collection_name)).to_be_visible()

    def click_add_task(self, collection_name: str, grant_name: str) -> SelectTaskTypePage:
        self.page.get_by_role("link", name=f"Add tasks to {collection_name}").click()
        form_type_page = SelectTaskTypePage(
            self.page,
            self.domain,
            grant_name=grant_name,
            collection_name=collection_name,
            section_title=DEFAULT_SECTION_NAME,
        )
        expect(form_type_page.heading).to_be_visible()
        return form_type_page

    def click_manage_tasks(self, collection_name: str, grant_name: str) -> CollectionDetailPage:
        self.page.get_by_role("link", name=re.compile(rf"Manage \d+ tasks for {collection_name}")).click()
        collection_detail_page = CollectionDetailPage(
            self.page, self.domain, grant_name=grant_name, collection_name=collection_name
        )
        expect(collection_detail_page.heading).to_be_visible()
        return collection_detail_page

    def click_view_submissions(self, collection_name: str) -> SubmissionsListPage:
        self.summary_row_submissions.get_by_role("link", name="View").click()
        submissions_list_page = SubmissionsListPage(self.page, self.domain, self.grant_name, collection_name)
        expect(submissions_list_page.heading).to_be_visible()
        return submissions_list_page


class AddCollectionPage(GrantDevelopersBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of this monitoring report?"),
        )

    def fill_in_collection_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of this monitoring report?").fill(name)

    def click_submit(self, grant_name: str) -> GrantDevelopersPage:
        self.page.get_by_role("button", name="Set up report").click()
        developers_page = GrantDevelopersPage(self.page, self.domain, grant_name=grant_name)
        expect(developers_page.heading).to_be_visible()
        return developers_page


class CollectionDetailPage(GrantDevelopersBasePage):
    collection_name: str
    test_form_button: Locator
    summary_row_submissions: Locator
    manage_sections_link: Locator
    back_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=collection_name),
        )
        self.collection_name = collection_name
        self.test_form_button = self.page.get_by_role("button", name="Preview report")
        self.add_section_button = self.page.get_by_role(
            "link", name="Split the form into sections of related tasks"
        ).or_(self.page.get_by_role("link", name="Add another section to the form"))
        self.back_link = self.page.get_by_role("link", name="Back")

    def click_back(self) -> "GrantDevelopersPage":
        # TODO: just put this on the base class and remove from child classes
        self.back_link.click()
        grant_developers_page = GrantDevelopersPage(self.page, self.domain, grant_name=self.grant_name)
        return grant_developers_page

    def check_section_exists(self, section_title: str) -> None:
        expect(self.page.get_by_role("heading", level=3, name=section_title, exact=True)).to_be_visible()

    def check_task_exists(self, section_title: str, task_title: str) -> None:
        expect(self.page.get_by_role("link", name=task_title, exact=True)).to_be_visible()

    def click_add_section(self) -> AddSectionPage:
        self.add_section_button.click()
        add_section_page = AddSectionPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=self.collection_name
        )
        return add_section_page

    def click_test_form(self) -> TasklistPage:
        self.test_form_button.click()
        tasklist_page = TasklistPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=self.collection_name
        )
        expect(tasklist_page.heading).to_be_visible()
        return tasklist_page

    def click_manage_form(self, form_name: str, section_title: str) -> ManageFormPage:
        self.page.get_by_role("link", name=form_name, exact=True).click()
        manage_form_page = ManageFormPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=section_title,
            form_name=form_name,
        )
        expect(manage_form_page.heading).to_be_visible()
        return manage_form_page

    def click_add_form(self, section_name: str) -> SelectTaskTypePage:
        self.page.get_by_role("link", name=f"Add a task to the “{section_name}” section").or_(
            self.page.get_by_role("link", name=f"Add another task to the “{section_name}” section")
        ).click()
        form_type_page = SelectTaskTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=section_name,
        )
        expect(form_type_page.heading).to_be_visible()
        return form_type_page


class SectionsListPage(GrantDevelopersBasePage):
    collection_name: str
    add_section_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{collection_name} Sections")
        )
        self.collection_name = collection_name
        self.add_section_button = self.page.get_by_role("button", name="Add a section")

    def click_add_section(self) -> AddSectionPage:
        self.add_section_button.click()
        add_section_page = AddSectionPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=self.collection_name
        )
        expect(add_section_page.heading).to_be_visible()
        return add_section_page

    def check_section_exists(self, section_title: str) -> None:
        expect(self.page.get_by_role("link", name=section_title)).to_be_visible()

    def click_manage_section(self, section_title: str) -> SectionDetailsPage:
        self.page.get_by_role("link", name=f"Manage {section_title}").click()
        section_detail_page = SectionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=section_title,
        )
        expect(section_detail_page.heading).to_be_visible()
        return section_detail_page


class AddSectionPage(GrantDevelopersBasePage):
    title: Locator
    collection_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the section?"),
        )
        self.collection_name = collection_name

    def fill_in_section_title(self, new_title: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the section?").fill(new_title)

    def click_submit(self, collection_name: str) -> CollectionDetailPage:
        self.page.get_by_role("button", name="Add section").click()
        collection_detail_page = CollectionDetailPage(self.page, self.domain, self.grant_name, self.collection_name)
        return collection_detail_page


class SectionDetailsPage(GrantDevelopersBasePage):
    add_form_button: Locator
    section_title: str
    collection_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{collection_name} {section_title}"),
        )
        self.section_title = section_title
        self.collection_name = collection_name
        self.add_form_button = self.page.get_by_role("button", name="Add a task")

    def click_add_form(self) -> SelectTaskTypePage:
        self.add_form_button.click()
        form_type_page = SelectTaskTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
        )
        expect(form_type_page.heading).to_be_visible()
        return form_type_page

    def check_form_exists(self, form_name: str) -> None:
        expect(self.page.get_by_role("term").filter(has_text=form_name)).to_be_visible()

    def click_manage_form(self, form_name: str) -> ManageFormPage:
        self.page.get_by_role("link", name="collection tasklist").click()

        collection_detail_page = CollectionDetailPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
        )
        manage_form_page = collection_detail_page.click_manage_form(
            form_name=form_name, section_title=self.section_title
        )
        return manage_form_page


class ManageFormPage(GrantDevelopersBasePage):
    section_title: str
    collection_name: str
    form_name: str
    add_question_button: Locator

    def __init__(
        self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str, form_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{section_title} {form_name}"),
        )
        self.section_title = section_title
        self.collection_name = collection_name
        self.form_name = form_name
        self.add_question_button = self.page.get_by_role("button", name="Add question")

    def click_add_question(self) -> SelectQuestionTypePage:
        self.add_question_button.click()
        select_question_type_page = SelectQuestionTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(select_question_type_page.heading).to_be_visible()
        return select_question_type_page

    def check_question_exists(self, question_name: str) -> None:
        expect(self.page.get_by_role("term").filter(has_text=question_name)).to_be_visible()

    def click_edit_question(self, question_name: str) -> "EditQuestionPage":
        self.page.get_by_role("link", name=question_name).click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class EditQuestionPage(GrantDevelopersBasePage):
    add_validation_button: Locator
    back_link: Locator

    def __init__(
        self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str, form_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Edit question"),
        )
        self.section_title = section_title
        self.collection_name = collection_name
        self.form_name = form_name
        self.add_validation_button = self.page.get_by_role("button", name="Add validation").or_(
            self.page.get_by_role("button", name="Add more validation")
        )
        self.back_link = self.page.get_by_role("link", name="Back")

    def click_add_validation(self) -> "AddValidationPage":
        self.add_validation_button.click()
        add_validation_page = AddValidationPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(add_validation_page.heading).to_be_visible()
        return add_validation_page

    def click_back(self) -> "ManageFormPage":
        self.back_link.click()
        manage_form_page = ManageFormPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(manage_form_page.heading).to_be_visible()
        return manage_form_page


class AddValidationPage(GrantDevelopersBasePage):
    add_validation_button: Locator

    def __init__(
        self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str, form_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add validation"),
        )
        self.section_title = section_title
        self.collection_name = collection_name
        self.form_name = form_name
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
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page


class SelectQuestionTypePage(GrantDevelopersBasePage):
    section_title: str
    collection_name: str
    form_name: str

    def __init__(
        self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str, form_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the type of the question?"),
        )
        self.section_title = section_title
        self.collection_name = collection_name
        self.form_name = form_name

    def click_question_type(self, question_type: str) -> None:
        self.page.get_by_role("radio", name=question_type).click()

    def click_continue(self) -> AddQuestionDetailsPage:
        self.page.get_by_role("button", name="Continue").click()
        question_details_page = AddQuestionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(question_details_page.heading).to_be_visible()
        return question_details_page


class AddQuestionDetailsPage(GrantDevelopersBasePage):
    section_title: str
    collection_name: str
    form_name: str

    def __init__(
        self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str, form_name: str
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Add question"),
        )
        self.section_title = section_title
        self.collection_name = collection_name
        self.form_name = form_name

    def fill_question_text(self, question_text: str) -> None:
        self.page.get_by_role("textbox", name="What is the question?").fill(question_text)

    def fill_question_name(self, question_name: str) -> None:
        self.page.get_by_role("textbox", name="Question name").fill(question_name)

    def fill_question_hint(self, question_hint: str) -> None:
        self.page.get_by_role("textbox", name="Question hint").fill(question_hint)

    def fill_data_source_items(self, items: list[str]) -> None:
        self.page.get_by_role("textbox", name="List of options").fill("\n".join(items))

    def click_fallback_option_checkbox(self) -> None:
        self.page.get_by_role(
            "checkbox", name="Include a final answer for users if none of the options are appropriate"
        ).click()

    def enter_fallback_option_text(self, text: str = "None of the above") -> None:
        self.page.get_by_role("textbox", name="Fallback option").fill(text)

    def click_submit(self) -> "EditQuestionPage":
        self.page.get_by_role("button", name="Add question").click()
        edit_question_page = EditQuestionPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(edit_question_page.heading).to_be_visible()
        return edit_question_page

    def click_back(self) -> ManageFormPage:
        self.page.get_by_role("link", name="Back").click()
        manage_form_page = ManageFormPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
            form_name=self.form_name,
        )
        expect(manage_form_page.heading).to_be_visible()
        return manage_form_page


class SelectTaskTypePage(GrantDevelopersBasePage):
    section_title: str
    collection_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str) -> None:
        super().__init__(page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name="Add a task"))
        self.section_title = section_title
        self.collection_name = collection_name

    def click_add_empty_task(self) -> None:
        self.page.get_by_role("radio", name="Add an empty task").click()

    def click_continue(self) -> AddFormDetailsPage:
        self.page.get_by_role("button", name="Continue").click()
        form_details_page = AddFormDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
        )
        expect(form_details_page.heading).to_be_visible()
        return form_details_page


class AddFormDetailsPage(GrantDevelopersBasePage):
    section_title: str
    collection_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the task?"),
        )
        self.section_title = section_title
        self.collection_name = collection_name

    def fill_in_task_name(self, task_name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the task?").fill(task_name)

    def click_add_task(self) -> CollectionDetailPage:
        self.page.get_by_role("button", name="Add task").click()
        collection_detail_page = CollectionDetailPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
        )
        expect(collection_detail_page.heading).to_be_visible()
        return collection_detail_page


class TasklistPage(GrantDevelopersBasePage):
    collection_name: str
    collection_status_box: Locator
    submit_button: Locator
    back_link: Locator

    def __init__(
        self,
        page: Page,
        domain: str,
        grant_name: str,
        collection_name: str,
    ) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=collection_name),
        )
        self.collection_name = collection_name
        self.collection_status_box = page.get_by_test_id("submission-status")
        self.submit_button = page.get_by_role("button", name="Submit")
        self.back_link = self.page.get_by_role("link", name="Back")

    def click_on_form(self, form_name: str) -> None:
        self.page.get_by_role("link", name=form_name).click()

    def click_submit(self) -> CollectionDetailPage:
        self.submit_button.click()
        collection_detail_page = CollectionDetailPage(self.page, self.domain, self.grant_name, self.collection_name)
        expect(collection_detail_page.heading).to_be_visible()
        return collection_detail_page

    def click_back(self) -> CollectionDetailPage:
        self.back_link.click()
        collection_detail_page = CollectionDetailPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=self.collection_name
        )
        expect(collection_detail_page.heading).to_be_visible()
        return collection_detail_page


class QuestionPage(GrantDevelopersBasePage):
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


class CheckYourAnswersPage(GrantDevelopersBasePage):
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

    def click_save_and_continue(self, collection_name: str) -> TasklistPage:
        self.save_and_continue_button.click()
        task_list_page = TasklistPage(self.page, self.domain, self.grant_name, collection_name=collection_name)
        expect(task_list_page.heading).to_be_visible()
        return task_list_page


class SubmissionsListPage(GrantDevelopersBasePage):
    collection_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{collection_name} Submissions"),
        )
        self.collection_name = collection_name

    def click_on_first_submission(self) -> ViewSubmissionPage:
        first_submission_reference = self.page.locator("[data-submission-link]").first.inner_text()
        return self.click_on_submission(first_submission_reference)

    def click_on_submission(self, collection_reference: str) -> ViewSubmissionPage:
        self.page.get_by_role("link", name=collection_reference).click()
        view_collection_page = ViewSubmissionPage(
            self.page, self.domain, self.grant_name, collection_reference=collection_reference
        )
        expect(view_collection_page.heading).to_be_visible()
        return view_collection_page


class ViewSubmissionPage(GrantDevelopersBasePage):
    collection_reference: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_reference: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{collection_reference} Submission"),
        )
        self.collection_reference = collection_reference

    def get_questions_list_for_form(self, form_name: str) -> Locator:
        return self.page.get_by_test_id(form_name)
