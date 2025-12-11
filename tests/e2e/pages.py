from __future__ import annotations

from abc import ABC

from playwright.sync_api import Locator, Page, expect

from tests.e2e.reports_pages import GrantReportsPage


class BasePage:
    domain: str
    page: Page

    def __init__(self, page: Page, domain: str) -> None:
        self.page = page
        self.domain = domain


class TopNavMixin(ABC):
    domain: str
    page: Page

    def click_grants(self) -> AllGrantsPage:
        # This should be the 'Show all grants' link, to be added shortly.
        self.page.get_by_role("link", name="Deliver grant funding").click()
        return AllGrantsPage(self.page, self.domain)


class LandingPage(TopNavMixin, BasePage):
    # TODO extend once there is more stuff on the landing page
    def navigate(self) -> None:
        self.page.goto(self.domain)


class RequestALinkToSignInPage(BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Access grant funding")
        self.email_address = self.page.get_by_role("textbox", name="Email address")
        self.request_a_link = self.page.get_by_role("button", name="Request sign in link")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/request-a-link-to-sign-in")
        expect(self.title).to_be_visible()

    def fill_email_address(self, email_address: str) -> None:
        self.email_address.fill(email_address)

    def click_request_a_link(self) -> None:
        self.request_a_link.click()


class SSOSignInPage(BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Deliver grant funding")
        self.sign_in = self.page.get_by_role("button", name="Sign in")

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/sso/sign-in")
        # If already logged in, this will redirect to /grants
        expect(
            self.title.or_(self.page.get_by_role("heading", name="Grants", exact=True)).or_(
                self.page.get_by_role("heading", name="Reports")
            )
        ).to_be_visible()

    def click_sign_in(self) -> None:
        self.sign_in.click()


class StubSSOEmailLoginPage(BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Local SSO Stub Login")
        self.email_address = self.page.get_by_role("textbox", name="Email address")
        self.sign_in = self.page.get_by_role("button", name="Sign in")

    def click_sign_in(self) -> None:
        self.sign_in.click()

    def fill_email_address(self, email_address: str) -> None:
        self.email_address.fill(email_address)

    def uncheck_platform_admin_checkbox(self) -> None:
        self.page.get_by_role("checkbox", name="Platform admin type login").uncheck()


class MicrosoftLoginBasePage(BasePage):
    email_address: str
    password: str

    def __init__(self, page: Page, domain: str, email_address: str, password: str) -> None:
        super().__init__(page, domain)
        self.email_address = email_address
        self.password = password


class MicrosoftLoginPageEmail(MicrosoftLoginBasePage):
    title: Locator
    email_input: Locator
    next_button: Locator

    def __init__(self, page: Page, domain: str, email_address: str, password: str) -> None:
        super().__init__(page, domain, email_address, password)
        self.title = self.page.get_by_role("heading", name="Sign in to your account")
        self.email_input = self.page.get_by_role("textbox", name="Email, phone, or Skype")
        self.next_button = self.page.get_by_role("button", name="Next")

    def fill_email_address(self) -> None:
        self.email_input.fill(self.email_address)

    def click_next(self) -> MicrosoftLoginPagePassword:
        self.next_button.click()
        password_page = MicrosoftLoginPagePassword(self.page, self.domain, self.email_address, self.password)
        expect(password_page.title).to_be_visible()
        return password_page


class MicrosoftLoginPagePassword(MicrosoftLoginBasePage):
    title: Locator
    password_input: Locator
    sign_in_button: Locator

    def __init__(self, page: Page, domain: str, email_address: str, password: str) -> None:
        super().__init__(page, domain, email_address, password)
        self.title = page.get_by_role("heading", name="Enter password")
        self.password_input = page.get_by_role("textbox", name=f"Enter the password for {self.email_address}")
        self.sign_in_button = page.get_by_role("button", name="Sign in")

    def fill_password(
        self,
    ) -> None:
        self.password_input.fill(self.password)

    def click_sign_in(self) -> None:
        self.sign_in_button.click()


class AllGrantsPage(TopNavMixin, BasePage):
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Grants", exact=True)

    def navigate(self) -> None:
        self.page.goto(f"{self.domain}/deliver/grants")
        expect(self.title).to_be_visible()

    def click_set_up_a_grant(self) -> GrantSetupIntroPage:
        self.page.get_by_role("button", name="Set up a grant").click()
        grant_setup_intro_page = GrantSetupIntroPage(self.page, self.domain)
        expect(grant_setup_intro_page.title).to_be_visible()
        return grant_setup_intro_page

    def check_grant_exists(self, grant_name: str) -> None:
        expect(self.page.get_by_role("link", name=grant_name)).to_be_visible()

    def check_grant_doesnt_exist(self, grant_name: str) -> None:
        expect(self.page.get_by_role("link", name=grant_name, exact=True)).not_to_be_visible()

    def click_grant(self, grant_name: str) -> GrantDashboardPage:
        self.page.get_by_role("link", name=grant_name).click()
        grant_dashboard_page = GrantDashboardPage(self.page, self.domain)
        expect(self.page.get_by_role("heading", name=grant_name)).to_be_visible()
        return grant_dashboard_page


class GrantSetupIntroPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Tell us about the grant")
        self.continue_button = self.page.get_by_role("button", name="Continue")

    def click_continue(self) -> GrantSetupGGISPage:
        self.continue_button.click()
        grant_setup_ggis_page = GrantSetupGGISPage(self.page, self.domain)
        expect(grant_setup_ggis_page.title).to_be_visible()
        return grant_setup_ggis_page


class GrantSetupGGISPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role(
            "heading", name="Do you have a Government Grants Information System (GGIS) reference number?"
        )
        self.yes_radio = self.page.get_by_role("radio", name="Yes")
        self.ggis_number_input = self.page.get_by_role("textbox", name="Enter your GGIS reference number")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def select_yes(self) -> None:
        self.yes_radio.click()

    def fill_ggis_number(self, ggis_number: str = "ABC-123") -> None:
        self.ggis_number_input.fill(ggis_number)

    def click_save_and_continue(self) -> GrantSetupNamePage:
        self.save_continue_button.click()
        grant_setup_name_page = GrantSetupNamePage(self.page, self.domain)
        expect(grant_setup_name_page.title).to_be_visible()
        return grant_setup_name_page


class GrantSetupNamePage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the name of this grant?")
        self.name_input = self.page.get_by_role("textbox", name="Enter the grant name")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def fill_name(self, name: str) -> None:
        self.name_input.fill(name)

    def click_save_and_continue(self) -> GrantSetupDescriptionPage:
        self.save_continue_button.click()
        grant_setup_description_page = GrantSetupDescriptionPage(self.page, self.domain)
        expect(grant_setup_description_page.title).to_be_visible()
        return grant_setup_description_page


class GrantSetupDescriptionPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the main purpose of this grant?")
        self.description_textarea = self.page.get_by_role("textbox", name="Enter the main purpose of this grant")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def fill_description(self, description: str = "Test grant description for E2E testing purposes.") -> None:
        self.description_textarea.fill(description)

    def click_save_and_continue(self) -> GrantSetupContactPage:
        self.save_continue_button.click()
        grant_setup_contact_page = GrantSetupContactPage(self.page, self.domain)
        expect(grant_setup_contact_page.title).to_be_visible()
        return grant_setup_contact_page


class GrantSetupContactPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Who is the main contact for this grant?")
        self.contact_name_input = self.page.get_by_role("textbox", name="Full name")
        self.contact_email_input = self.page.get_by_role("textbox", name="Email address")
        self.save_continue_button = self.page.get_by_role("button", name="Save and continue")

    def fill_contact_name(self, name: str = "Test Contact") -> None:
        self.contact_name_input.fill(name)

    def fill_contact_email(self, email: str = "test.contact@communities.gov.uk") -> None:
        self.contact_email_input.fill(email)

    def click_save_and_continue(self) -> GrantSetupCheckYourAnswersPage:
        self.save_continue_button.click()
        grant_setup_check_your_answers_page = GrantSetupCheckYourAnswersPage(self.page, self.domain)
        expect(grant_setup_check_your_answers_page.title).to_be_visible()
        return grant_setup_check_your_answers_page


class GrantSetupCheckYourAnswersPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Check your answers")
        self.add_grant_button = self.page.get_by_role("button", name="Confirm and set up grant")

    def click_add_grant(self) -> GrantDashboardPage:
        self.add_grant_button.click()
        grant_dashboard_page = GrantDashboardPage(self.page, self.domain)
        return grant_dashboard_page


class GrantSetupConfirmationPage(TopNavMixin, BasePage):
    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.locator("h1:has-text('added')")
        self.continue_button = self.page.get_by_role("link", name="Continue to grant home")

    def click_continue(self) -> GrantDashboardPage:
        self.continue_button.click()
        return GrantDashboardPage(self.page, self.domain)


class GrantDashboardBasePage(TopNavMixin, BasePage):
    settings_nav: Locator
    reports_nav: Locator
    grant_team_nav: Locator
    sign_out_nav: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.settings_nav = self.page.get_by_role("link", name="Grant details")
        self.reports_nav = self.page.get_by_role("link", name="Reports")
        self.grant_team_nav = self.page.get_by_role("link", name="Team")
        self.sign_out_nav = self.page.get_by_role("link", name="Sign out")

    def click_settings(self, grant_name: str) -> GrantDetailsPage:
        self.settings_nav.click()
        grant_details_page = GrantDetailsPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_details_page.page.get_by_role("heading", name=f"{grant_name} Grant details")).to_be_visible()
        return grant_details_page

    def check_grant_name(self, grant_name: str) -> None:
        expect(self.page.get_by_role("heading", name=grant_name)).to_be_visible()

    def click_reports(self, grant_name: str) -> GrantReportsPage:
        self.reports_nav.click()
        grant_reports_page = GrantReportsPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_reports_page.heading).to_be_visible()
        return grant_reports_page

    def click_grant_team(self) -> GrantTeamPage:
        self.reports_nav.click()
        grant_team_page = GrantTeamPage(self.page, self.domain)
        expect(grant_team_page.title).to_be_visible()
        return grant_team_page

    def click_sign_out(self) -> SSOSignInPage:
        self.sign_out_nav.click()
        sso_sign_in_page = SSOSignInPage(self.page, self.domain)
        expect(sso_sign_in_page.title).to_be_visible()
        return sso_sign_in_page


class GrantDashboardPage(GrantDashboardBasePage):
    pass


class GrantDetailsPage(GrantDashboardBasePage):
    change_name_link: Locator
    change_ggis_link: Locator
    change_description_link: Locator
    change_contact_link: Locator
    grant_name: str
    title: Locator

    def __init__(self, page: Page, domain: str, grant_name: str) -> None:
        super().__init__(page, domain)
        self.title = page.get_by_role("heading", name=f"{grant_name} Grant details")
        self.change_name_link = self.page.get_by_role("link", name="Change grant name")
        self.change_ggis_link = self.page.get_by_role("link", name="Change GGIS reference number")
        self.change_description_link = self.page.get_by_role("link", name="Change main purpose")
        self.change_contact_link = self.page.get_by_role("link", name="Change main contact")

    def click_change_grant_ggis(self, existing_ggis_ref: str | None) -> ChangeGrantGGISPage:
        self.change_ggis_link.click()
        change_ggis_page = ChangeGrantGGISPage(self.page, self.domain)
        expect(change_ggis_page.title).to_be_visible()
        if existing_ggis_ref:
            expect(change_ggis_page.ggis_textbox).to_be_visible()
            expect(change_ggis_page.ggis_textbox).to_have_value(existing_ggis_ref)
        else:
            expect(change_ggis_page.ggis_textbox).not_to_be_visible()
        return change_ggis_page

    def click_change_grant_name(self, grant_name: str) -> ChangeGrantNamePage:
        self.change_name_link.click()
        change_grant_name_page = ChangeGrantNamePage(self.page, self.domain)
        expect(change_grant_name_page.title).to_be_visible()
        expect(change_grant_name_page.grant_name_textbox).to_have_value(grant_name)
        return change_grant_name_page

    def click_change_grant_contact_details(
        self, existing_contact_name: str, existing_contact_email: str
    ) -> ChangeGrantMainContactPage:
        self.change_contact_link.click()
        change_grant_main_contact_page = ChangeGrantMainContactPage(self.page, self.domain)
        expect(change_grant_main_contact_page.title).to_be_visible()
        expect(change_grant_main_contact_page.contact_name_textbox).to_have_value(existing_contact_name)
        expect(change_grant_main_contact_page.contact_email_textbox).to_have_value(existing_contact_email)

        return change_grant_main_contact_page

    def click_change_grant_description(self, existing_description: str) -> ChangeGrantDescriptionPage:
        self.change_description_link.click()
        change_grant_description_page = ChangeGrantDescriptionPage(self.page, self.domain)
        expect(change_grant_description_page.title).to_be_visible()
        expect(change_grant_description_page.grant_description_textbox).to_have_value(existing_description)
        return change_grant_description_page


class ChangeGrantNamePage(GrantDashboardBasePage):
    backlink: Locator
    title: Locator
    grant_name_textbox: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the name of this grant?")
        self.grant_name_textbox = page.get_by_role("textbox", name="Enter the grant name")

    def fill_in_grant_name(self, name: str) -> None:
        self.grant_name_textbox.fill(name)

    def click_submit(self, grant_name: str) -> GrantDetailsPage:
        self.page.get_by_role("button", name="Update grant name").click()
        grant_details_page = GrantDetailsPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_details_page.title).to_be_visible()
        return grant_details_page


class ChangeGrantGGISPage(GrantDashboardBasePage):
    backlink: Locator
    title: Locator
    ggis_textbox: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the GGIS reference number?")
        self.ggis_textbox = self.page.get_by_role("textbox", name="Enter your GGIS reference number")

    def fill_ggis_number(self, new_ggis_ref: str) -> None:
        self.ggis_textbox.fill(new_ggis_ref)

    def click_submit(self, grant_name: str) -> GrantDetailsPage:
        self.page.get_by_role("button", name="Update GGIS reference number").click()
        grant_details_page = GrantDetailsPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_details_page.title).to_be_visible()
        return grant_details_page


class ChangeGrantDescriptionPage(GrantDashboardBasePage):
    backlink: Locator
    title: Locator
    grant_description_textbox: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="What is the main purpose of this grant?")
        self.grant_description_textbox = page.get_by_role("textbox", name="Enter the main purpose of this grant")

    def fill_in_grant_description(self, description: str) -> None:
        self.grant_description_textbox.fill(description)

    def click_submit(self, grant_name: str) -> GrantDetailsPage:
        self.page.get_by_role("button", name="Update main purpose").click()
        grant_details_page = GrantDetailsPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_details_page.title).to_be_visible()
        return grant_details_page


class ChangeGrantMainContactPage(GrantDashboardBasePage):
    backlink: Locator
    title: Locator
    contact_name_textbox: Locator
    contact_email_textbox: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = self.page.get_by_role("heading", name="Who is the main contact for this grant?")
        self.contact_name_textbox = page.get_by_role("textbox", name="Full name")
        self.contact_email_textbox = page.get_by_role("textbox", name="Email address")

    def fill_contact_name(self, name: str) -> None:
        self.contact_name_textbox.fill(name)

    def fill_contact_email(self, email: str) -> None:
        self.contact_email_textbox.fill(email)

    def click_submit(self, grant_name: str) -> GrantDetailsPage:
        self.page.get_by_role("button", name="Update main contact").click()
        grant_details_page = GrantDetailsPage(self.page, self.domain, grant_name=grant_name)
        expect(grant_details_page.title).to_be_visible()
        return grant_details_page


class GrantTeamPage(GrantDashboardBasePage):
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = page.get_by_role("heading", name="Team")

    def click_add_grant_team_member(self) -> AddGrantTeamMemberPage:
        self.page.get_by_role("button", name="Add grant team member").click()
        add_grant_team_member_page = AddGrantTeamMemberPage(self.page, self.domain)
        expect(add_grant_team_member_page.title).to_be_visible()
        return add_grant_team_member_page


class AddGrantTeamMemberPage(GrantDashboardBasePage):
    title: Locator

    def __init__(self, page: Page, domain: str) -> None:
        super().__init__(page, domain)
        self.title = page.get_by_role("heading", name="What’s their email address?")

    def fill_in_user_email(self, email_address: str) -> None:
        self.page.get_by_role("textbox").fill(email_address)

    def click_continue(self) -> GrantTeamPage:
        self.page.get_by_role("button", name="Continue").click()
        grant_team_page = GrantTeamPage(self.page, self.domain)
        expect(grant_team_page.page.get_by_role("heading", name="Grant team member added")).to_be_visible()
        expect(grant_team_page.page.get_by_role("alert", name="Success")).to_be_visible()
        return grant_team_page
