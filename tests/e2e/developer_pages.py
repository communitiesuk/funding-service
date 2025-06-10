from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


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

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} Developers")
        )
        self.manage_collections_link = self.page.get_by_role("link", name="Manage")

    def click_manage_collections(self, grant_name: str) -> ListCollectionsPage:
        self.manage_collections_link.click()
        list_collections_page = ListCollectionsPage(self.page, self.domain, self.grant_name)
        expect(list_collections_page.heading).to_be_visible()
        return list_collections_page


class ListCollectionsPage(GrantDevelopersBasePage):
    add_collection_button: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} collections")
        )
        self.add_collection_button = self.page.get_by_role("button", name="Add collection")

    def click_add_collection(self) -> AddCollectionPage:
        self.add_collection_button.click()
        add_collection_page = AddCollectionPage(self.page, self.domain, grant_name=self.grant_name)
        expect(add_collection_page.heading).to_be_visible()
        return add_collection_page

    def check_collection_exists(self, collection_name: str) -> None:
        expect(self.page.get_by_role("link", name=collection_name)).to_be_visible()

    def click_on_collection(self, collection_name: str, grant_name: str) -> CollectionDetailPage:
        self.page.get_by_role("link", name=collection_name).click()
        collection_detail_page = CollectionDetailPage(
            self.page, self.domain, grant_name=grant_name, collection_name=collection_name
        )
        expect(collection_detail_page.heading).to_be_visible()
        return collection_detail_page


class AddCollectionPage(GrantDevelopersBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the collection?"),
        )

    def fill_in_collection_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the collection?").fill(name)

    def click_submit(self, grant_name: str) -> ListCollectionsPage:
        self.page.get_by_role("button", name="Set up collection").click()
        list_collections_page = ListCollectionsPage(self.page, self.domain, grant_name=grant_name)
        expect(list_collections_page.heading).to_be_visible()
        return list_collections_page


class CollectionDetailPage(GrantDevelopersBasePage):
    collection_name: str
    preview_collection_button: Locator
    summary_row_submissions: Locator
    manage_sections_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=collection_name),
        )
        self.collection_name = collection_name
        self.manage_sections_link = self.page.get_by_role("link", name="manage sections")
        self.preview_collection_button = self.page.get_by_role("button", name="Preview this collection")
        self.summary_row_submissions = page.locator("div.govuk-summary-list__row").filter(
            has=page.get_by_text("Submissions")
        )

    def click_view_submissions(self) -> SubmissionsListPage:
        self.summary_row_submissions.get_by_role("link", name="View").click()
        submissions_list_page = SubmissionsListPage(self.page, self.domain, self.grant_name, self.collection_name)
        expect(submissions_list_page.heading).to_be_visible()
        return submissions_list_page

    def check_section_exists(self, section_title: str) -> None:
        expect(self.page.get_by_role("link", name=section_title)).to_be_visible()

    def click_add_section(self) -> AddSectionPage:
        self.manage_sections_link.click()
        list_sections_page = SectionsListPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=self.collection_name
        )
        add_section_page = list_sections_page.click_add_section()
        return add_section_page

    def click_preview_collection(self) -> TasklistPage:
        self.preview_collection_button.click()
        tasklist_page = TasklistPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=self.collection_name
        )
        expect(tasklist_page.heading).to_be_visible()
        return tasklist_page

    def click_manage_form(self, form_name: str, section_title: str) -> ManageFormPage:
        self.page.get_by_role("link", name=form_name).click()
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
        add_section_page = AddSectionPage(self.page, self.domain, grant_name=self.grant_name)
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

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the section?"),
        )

    def fill_in_section_title(self, new_title: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the section?").fill(new_title)

    def click_submit(self, collection_name: str) -> SectionsListPage:
        self.page.get_by_role("button", name="Add section").click()
        sections_list_page = SectionsListPage(
            self.page, self.domain, grant_name=self.grant_name, collection_name=collection_name
        )
        expect(sections_list_page.page.get_by_role("heading", name=f"{collection_name} Section")).to_be_visible()
        return sections_list_page


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
        self.add_form_button = self.page.get_by_role("button", name="Add a form")

    def click_add_form(self) -> SelectFormTypePage:
        self.add_form_button.click()
        form_type_page = SelectFormTypePage(
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

    def click_submit(self) -> ManageFormPage:
        self.page.get_by_role("button", name="Submit").click()
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


class SelectFormTypePage(GrantDevelopersBasePage):
    section_title: str
    collection_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_name: str, section_title: str) -> None:
        super().__init__(page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name="Add a form"))
        self.section_title = section_title
        self.collection_name = collection_name

    def click_add_empty_form(self) -> None:
        self.page.get_by_role("radio", name="Add an empty form").click()

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
            heading=page.get_by_role("heading", name="What is the name of the form?"),
        )
        self.section_title = section_title
        self.collection_name = collection_name

    def fill_in_form_name(self, form_name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the form?").fill(form_name)

    def click_add_form(self) -> SectionDetailsPage:
        self.page.get_by_role("button", name="Add form").click()
        section_details_page = SectionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            collection_name=self.collection_name,
            section_title=self.section_title,
        )
        expect(section_details_page.heading).to_be_visible()
        return section_details_page


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

    def click_submit(self) -> SubmitSubmissionConfirmationPage:
        self.submit_button.click()
        confirmation_page = SubmitSubmissionConfirmationPage(self.page, self.domain, self.grant_name)
        expect(confirmation_page.heading).to_be_visible()
        return confirmation_page

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

    def respond_to_question(self, answer: str) -> None:
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
        self.mark_as_complete_yes = page.get_by_role("radio", name="Yes, I’ve completed this section")

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

    def click_on_collection(self, collection_reference: str) -> ViewCollectionResponsesPage:
        self.page.get_by_role("link", name=collection_reference).click()
        view_collection_page = ViewCollectionResponsesPage(
            self.page, self.domain, self.grant_name, collection_reference=collection_reference
        )
        expect(view_collection_page.heading).to_be_visible()
        return view_collection_page


class ViewCollectionResponsesPage(GrantDevelopersBasePage):
    collection_reference: str

    def __init__(self, page: Page, domain: str, grant_name: str, collection_reference: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{collection_reference} Collection"),
        )
        self.collection_reference = collection_reference

    def get_questions_list_for_form(self, form_name: str) -> Locator:
        return self.page.get_by_test_id(form_name)


class SubmitSubmissionConfirmationPage(GrantDevelopersBasePage):
    collection_reference: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="Submission submitted"),
        )
        self.collection_reference = page.get_by_test_id("submission-reference")
