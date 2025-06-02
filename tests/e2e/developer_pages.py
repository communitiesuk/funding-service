from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class GrantDevelopersPage:
    domain: str
    page: Page
    manage_schemas_link: Locator

    def __init__(self, page: Page, domain: str) -> None:
        self.page = page
        self.domain = domain
        self.manage_schemas_link = self.page.get_by_role("link", name="Manage")

    def click_manage_schemas(self, grant_name: str) -> GrantManageSchemasPage:
        self.manage_schemas_link.click()
        manage_schemas_page = GrantManageSchemasPage(self.page, self.domain)
        expect(manage_schemas_page.page.get_by_role("heading", name=f"{grant_name} Schemas")).to_be_visible()
        return manage_schemas_page


class GrantManageSchemasPage(GrantDevelopersPage):
    add_schema_link: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.add_schema_link = self.page.get_by_role("link", name="add a schema")

    def click_add_schema(self) -> AddSchemaPage:
        self.add_schema_link.click()
        add_schema_page = AddSchemaPage(self.page, self.domain)
        expect(self.page.get_by_role("heading", name="What is the name of the schema?")).to_be_visible()
        return add_schema_page

    def check_schema_exists(self, schema_name: str) -> None:
        expect(self.page.get_by_role("link", name=schema_name)).to_be_visible()

    def click_on_schema(self, schema_name: str, grant_name: str) -> SchemaDetailPage:
        self.page.get_by_role("link", name=schema_name).click()
        schema_detail_page = SchemaDetailPage(self.page, self.domain, schema_name)
        expect(schema_detail_page.page.get_by_role("heading", name=f"{grant_name} {schema_name}")).to_be_visible()
        return schema_detail_page


class AddSchemaPage(GrantDevelopersPage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the name of the schema?")

    def fill_in_schema_name(self, name: str) -> None:
        self.page.get_by_role("textbox", name="name").fill(name)

    def click_submit(self, grant_name: str) -> GrantManageSchemasPage:
        self.page.get_by_role("button", name="Set up schema").click()
        manage_schemas_page = GrantManageSchemasPage(self.page, self.domain)
        expect(manage_schemas_page.page.get_by_role("heading", name=f"{grant_name} Schemas")).to_be_visible()
        return manage_schemas_page


class SchemaDetailPage(GrantDevelopersPage):
    schema_name: str

    def __init__(self, page: Page, domain: str, schema_name: str) -> None:
        super().__init__(page, domain)
        self.schema_name = schema_name
