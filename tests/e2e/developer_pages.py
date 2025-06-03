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
    manage_schemas_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} Developers")
        )
        self.manage_schemas_link = self.page.get_by_role("link", name="Manage")

    def click_manage_schemas(self, grant_name: str) -> GrantManageSchemasPage:
        self.manage_schemas_link.click()
        manage_schemas_page = GrantManageSchemasPage(self.page, self.domain, self.grant_name)
        expect(manage_schemas_page.heading).to_be_visible()
        return manage_schemas_page


class GrantManageSchemasPage(GrantDevelopersBasePage):
    add_schema_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} Schemas")
        )
        self.add_schema_link = self.page.get_by_role("link", name="add a schema")

    def click_add_schema(self) -> AddSchemaPage:
        self.add_schema_link.click()
        add_schema_page = AddSchemaPage(self.page, self.domain, grant_name=self.grant_name)
        expect(add_schema_page.heading).to_be_visible()
        return add_schema_page

    def check_schema_exists(self, schema_name: str) -> None:
        expect(self.page.get_by_role("link", name=schema_name)).to_be_visible()

    def click_on_schema(self, schema_name: str, grant_name: str) -> SchemaDetailPage:
        self.page.get_by_role("link", name=schema_name).click()
        schema_detail_page = SchemaDetailPage(self.page, self.domain, grant_name=grant_name, schema_name=schema_name)
        expect(schema_detail_page.heading).to_be_visible()
        return schema_detail_page


class AddSchemaPage(GrantDevelopersBasePage):
    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the schema?"),
        )

    def fill_in_schema_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the schema?").fill(name)

    def click_submit(self, grant_name: str) -> GrantManageSchemasPage:
        self.page.get_by_role("button", name="Set up schema").click()
        manage_schemas_page = GrantManageSchemasPage(self.page, self.domain, grant_name=grant_name)
        expect(manage_schemas_page.heading).to_be_visible()
        return manage_schemas_page


class SchemaDetailPage(GrantDevelopersBasePage):
    schema_name: str
    add_section_link: Locator

    def __init__(self, page: Page, domain: str, grant_name: str, schema_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{grant_name} {schema_name}")
        )
        self.schema_name = schema_name
        self.add_section_link = self.page.get_by_role("link", name="add a section")

    def check_section_exists(self, section_title: str) -> bool:
        return self.page.get_by_role("link", name=section_title).is_visible()

    def click_add_section(self) -> AddSectionPage:
        self.add_section_link.click()
        add_section_page = AddSectionPage(self.page, self.domain, grant_name=self.grant_name)
        expect(add_section_page.heading).to_be_visible()
        return add_section_page


class SectionsListPage(GrantDevelopersBasePage):
    schema_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, schema_name: str) -> None:
        super().__init__(
            page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name=f"{schema_name} Sections")
        )
        self.schema_name = schema_name

    def check_section_exists(self, section_title: str) -> bool:
        return self.page.get_by_role("listitem", name=section_title).is_visible()

    def click_manage_section(self, section_title: str) -> SectionDetailsPage:
        self.page.get_by_role("link", name=f"Manage {section_title}").click()
        section_detail_page = SectionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            schema_name=self.schema_name,
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

    def click_submit(self, schema_name: str) -> SectionsListPage:
        self.page.get_by_role("button", name="Add section").click()
        sections_list_page = SectionsListPage(
            self.page, self.domain, grant_name=self.grant_name, schema_name=schema_name
        )
        expect(sections_list_page.page.get_by_role("heading", name=f"{schema_name} Section")).to_be_visible()
        return sections_list_page


class SectionDetailsPage(GrantDevelopersBasePage):
    add_form_link: Locator
    section_title: str
    schema_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, schema_name: str, section_title: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name=f"{schema_name} {section_title}"),
        )
        self.section_title = section_title
        self.schema_name = schema_name
        self.add_form_link = self.page.get_by_role("link", name="add a form")

    def click_add_form(self) -> SelectFormTypePage:
        self.add_form_link.click()
        form_type_page = SelectFormTypePage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            schema_name=self.schema_name,
            section_title=self.section_title,
        )
        expect(form_type_page.heading).to_be_visible()
        return form_type_page

    def check_form_exists(self, form_name: str) -> bool:
        return self.page.get_by_role("listitem", name=form_name).is_visible()


class SelectFormTypePage(GrantDevelopersBasePage):
    section_title: str
    schema_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, schema_name: str, section_title: str) -> None:
        super().__init__(page, domain, grant_name=grant_name, heading=page.get_by_role("heading", name="Add a form"))
        self.section_title = section_title
        self.schema_name = schema_name

    def click_add_empty_form(self) -> None:
        self.page.get_by_role("radio", name="Add an empty form").click()

    def click_continue(self) -> FormDetailsPage:
        self.page.get_by_role("button", name="Continue").click()
        form_details_page = FormDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            schema_name=self.schema_name,
            section_title=self.section_title,
        )
        expect(form_details_page.heading).to_be_visible()
        return form_details_page


class FormDetailsPage(GrantDevelopersBasePage):
    section_title: str
    schema_name: str

    def __init__(self, page: Page, domain: str, grant_name: str, schema_name: str, section_title: str) -> None:
        super().__init__(
            page,
            domain,
            grant_name=grant_name,
            heading=page.get_by_role("heading", name="What is the name of the form?"),
        )
        self.section_title = section_title
        self.schema_name = schema_name

    def fill_in_form_name(self, form_name: str) -> None:
        self.page.get_by_role("textbox", name="What is the name of the form?").fill(form_name)

    def click_add_form(self) -> SectionDetailsPage:
        self.page.get_by_role("button", name="Add form").click()
        section_details_page = SectionDetailsPage(
            self.page,
            self.domain,
            grant_name=self.grant_name,
            schema_name=self.schema_name,
            section_title=self.section_title,
        )
        expect(section_details_page.heading).to_be_visible()
        return section_details_page
