import re

from playwright.sync_api import Page

from app.common.data.types import CollectionStatusEnum, GrantStatusEnum
from tests.e2e.dataclasses import GrantScenario
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDashboardPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AdminCollectionLifecycleTasklistPage,
    MarkAsOnboardingWithFundingServicePage,
    OrganisationSetupRow,
    OverrideGrantRecipientCertifiersPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    PreAwardFormSectionsPage,
    ReportSectionsPage,
    SetPrivacyPolicyPage,
    SetReportingDatesPage,
    SetSubmissionDatesPage,
    SetUpDataProvidersPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
)


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


def navigate_to_pre_award_sections_page(
    page: Page, domain: str, grant_name: str, form_name: str
) -> PreAwardFormSectionsPage:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_pre_award_forms_page = grant_dashboard_page.click_pre_award(grant_name)
    form_sections_page = grant_pre_award_forms_page.click_manage_sections(grant_name=grant_name, form_name=form_name)
    return form_sections_page


def create_collection(
    page: Page,
    domain: str,
    grant_id: str,
    grant_name: str,
    collection_name: str,
    grant_dashboard_page: GrantDashboardPage,
) -> tuple[str, AdminCollectionLifecycleTasklistPage]:
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    choose_method_page = grant_reports_page.click_add_report()
    add_report_page = choose_method_page.click_create_new()
    add_report_page.fill_in_report_name(collection_name)
    grant_reports_page = add_report_page.click_submit(grant_name)
    grant_reports_page.check_report_exists(collection_name)

    page.get_by_role("link", name="0 data sets").click()
    collection_id = extract_uuid_from_url(page.url, r"/reports/(?P<uuid>[a-f0-9-]+)")
    tasklist_page = AdminCollectionLifecycleTasklistPage(page, domain, grant_id, collection_id)
    return collection_id, tasklist_page


def create_organisation(page: Page, domain: str, grant_id: str, collection_id: str, scenario: GrantScenario) -> None:
    assert scenario.org_name and scenario.org_external_id

    set_up_orgs_page = SetUpOrganisationsPage(page, domain, grant_id, collection_id)
    set_up_orgs_page.navigate()
    set_up_orgs_page.fill_organisations(
        [OrganisationSetupRow(scenario.org_external_id, scenario.org_name, "Central Government")]
    )
    set_up_orgs_page.click_set_up_organisations()


def create_grant_recipient(page: Page, domain: str, grant_id: str, collection_id: str, scenario: GrantScenario) -> None:
    assert scenario.org_name

    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, grant_id, collection_id)
    set_up_grant_recipients_page.navigate()
    set_up_grant_recipients_page.select_organisation(scenario.org_name)
    set_up_grant_recipients_page.select_status(scenario.recipient_status)
    set_up_grant_recipients_page.click_set_up_grant_recipients()


def invite_data_providers(page: Page, domain: str, grant_id: str, collection_id: str, scenario: GrantScenario) -> None:
    assert scenario.org_name

    tsv_rows = "\n".join(f"{scenario.org_name}\t{r.full_name}\t{r.email}" for r in scenario.recipients)
    tsv_data = f"organisation-name\tfull-name\temail-address\n{tsv_rows}\n"
    setup_data_providers_page = SetUpDataProvidersPage(page, domain, grant_id, collection_id)
    setup_data_providers_page.navigate()
    setup_data_providers_page.fill_users_tsv_data(tsv_data)
    setup_data_providers_page.click_set_up_users()


def override_certifiers(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    tasklist_page: AdminCollectionLifecycleTasklistPage,
    scenario: GrantScenario,
) -> None:
    assert scenario.org_name and scenario.recipients

    tasklist_page.navigate()
    tasklist_page.click_task("Override certifiers for this grant")
    override_certifiers_page = OverrideGrantRecipientCertifiersPage(page, domain, grant_id, collection_id)
    override_certifiers_page.select_organisation(scenario.org_name)
    override_certifiers_page.complete_user_details(scenario.recipients[0].full_name, scenario.recipients[0].email)
    override_certifiers_page.click_add_certifier()


def set_reporting_and_submission_dates(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    collection_name: str,
    tasklist_page: AdminCollectionLifecycleTasklistPage,
) -> None:
    tasklist_page.navigate()
    tasklist_page.click_task("Set reporting dates")
    set_reporting_dates_page = SetReportingDatesPage(page, domain, grant_id, collection_id)
    set_reporting_dates_page.set_reporting_dates_for_open_report()
    set_reporting_dates_page.click_save_dates(report_name=collection_name)

    tasklist_page.navigate()
    tasklist_page.click_task("Set submission dates")
    set_submission_dates_page = SetSubmissionDatesPage(page, domain, grant_id, collection_id)
    set_submission_dates_page.set_submission_dates_for_open_report()
    set_submission_dates_page.click_save_dates(report_name=collection_name)


def mark_as_onboarding(
    page: Page, domain: str, grant_id: str, collection_id: str, tasklist_page: AdminCollectionLifecycleTasklistPage
) -> None:
    tasklist_page.navigate()
    tasklist_page.click_task("Mark as onboarding with Funding Service")
    mark_as_onboarding_page = MarkAsOnboardingWithFundingServicePage(page, domain, grant_id, collection_id)
    mark_as_onboarding_page.click_mark_as_onboarding()


def set_privacy_policy(
    page: Page, domain: str, grant_id: str, collection_id: str, tasklist_page: AdminCollectionLifecycleTasklistPage
) -> None:
    tasklist_page.navigate()
    tasklist_page.click_task("Set privacy policy")
    set_privacy_policy_page = SetPrivacyPolicyPage(page, domain, grant_id, collection_id)
    set_privacy_policy_page.fill_privacy_policy_markdown("https://www.gov.uk/help/privacy-notice")
    set_privacy_policy_page.click_save_privacy_policy()


def set_grant_and_collection_live(page: Page, domain: str, grant_id: str, collection_id: str) -> None:
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status(GrantStatusEnum.LIVE)
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status(CollectionStatusEnum.OPEN)
    report_settings_page.click_save()
