import re

from playwright.sync_api import Page, expect

from app.common.data.types import CollectionStatusEnum, GrantRecipientStatusEnum, GrantStatusEnum
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import CollectionConfig, DataProviderConfig, OrganisationConfig, SectionDict
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDashboardPage, GrantTeamPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AdminCollectionLifecycleTasklistPage,
    GrantPreAwardFormsPage,
    GrantReportsPage,
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

# --- Build core entities --------------------------------------------------


def create_grant(new_grant_name: str, grant_name_uuid: str, all_grants_page: AllGrantsPage) -> GrantDashboardPage:
    """Create a new grant via the "Set up a grant" journey."""
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


def create_collection(
    page: Page,
    domain: str,
    grant_name: str,
    collection: CollectionConfig,
) -> str:
    """Create a collection of the type "record", with its sections/questions if any are given. Returns collection_id."""
    if not (grant_name and collection.name):
        raise ValueError("create_collection requires grant_name and collection.name")

    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    choose_method_page = grant_reports_page.click_add_report()
    add_report_page = choose_method_page.click_create_new()
    add_report_page.fill_in_report_name(collection.name)
    grant_reports_page = add_report_page.click_submit(grant_name)
    grant_reports_page.check_report_exists(collection.name)

    if collection.sections:
        _add_sections(page, domain, collection.sections, grant_name, collection.name, grant_reports_page)
        grant_reports_page = navigate_to_report_sections_page(
            page, domain, grant_name, collection.name
        ).click_reports_breadcrumb()

    page.get_by_role("link", name="0 data sets").click()
    return extract_uuid_from_url(page.url, r"/reports/(?P<uuid>[a-f0-9-]+)")


def create_application_collection(page: Page, domain: str, grant_name: str, collection: CollectionConfig) -> str:
    """Create an collection of the type "application", with its sections/questions if any are given. Returns
    collection_id."""
    if not (grant_name and collection.name):
        raise ValueError("create_application_collection requires grant_name and collection.name")

    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    pre_award_forms_page = grant_dashboard_page.click_pre_award(grant_name)
    method_page = pre_award_forms_page.click_add_form()
    add_form_page = method_page.click_create_new()
    add_form_page.fill_in_form_name(collection.name)
    pre_award_forms_page = add_form_page.click_submit(grant_name)

    if collection.sections:
        _add_sections(page, domain, collection.sections, grant_name, collection.name, pre_award_forms_page)

    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    pre_award_forms_page = grant_dashboard_page.click_pre_award(grant_name)
    pre_award_forms_page.click_manage_settings(collection.name)
    return extract_uuid_from_url(page.url, r"/applications/(?P<uuid>[a-f0-9-]+)")


def create_organisations(
    page: Page, domain: str, grant_id: str, collection_id: str, organisations: list[OrganisationConfig]
) -> None:
    """Set up the given organisations against the collection."""
    if not organisations:
        raise ValueError("create_organisations requires organisations")

    rows = [OrganisationSetupRow(o.external_id, o.name, o.type) for o in organisations]

    set_up_orgs_page = SetUpOrganisationsPage(page, domain, grant_id, collection_id)
    set_up_orgs_page.navigate()
    set_up_orgs_page.fill_organisations(rows)
    if len(rows) == 1:
        set_up_orgs_page.click_set_up_organisations()
    else:
        set_up_orgs_page.click_set_up_organisations(expected_organisations_created=len(rows))


def create_grant_recipients(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    organisations: list[OrganisationConfig],
) -> None:
    """Make the given organisations grant recipients."""
    if not organisations:
        raise ValueError("create_grant_recipients requires organisations")

    # The "set up grant recipients" step sets one status per bulk selection
    organisations_by_status: dict[GrantRecipientStatusEnum, list[OrganisationConfig]] = {}
    for organisation in organisations:
        organisations_by_status.setdefault(organisation.grant_recipient_status, []).append(organisation)

    for status, organisations_with_status in organisations_by_status.items():
        org_names = [o.name for o in organisations_with_status]

        set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, grant_id, collection_id)
        set_up_grant_recipients_page.navigate()
        if len(org_names) == 1:
            set_up_grant_recipients_page.select_organisation(org_names[0])
        else:
            set_up_grant_recipients_page.select_organisations(org_names)
        set_up_grant_recipients_page.select_status(status)
        if len(org_names) == 1:
            set_up_grant_recipients_page.click_set_up_grant_recipients()
        else:
            expected_message = f"Created {len(org_names)} grant recipients and {len(org_names)} test grant recipients."
            set_up_grant_recipients_page.click_set_up_grant_recipients(expected_message=expected_message)


def invite_data_providers(
    page: Page, domain: str, grant_id: str, collection_id: str, organisations: list[OrganisationConfig]
) -> None:
    """Invite each organisation's data providers, in one TSV upload covering every organisation. Does nothing if
    no organisation has any data providers."""
    tsv_rows = "\n".join(
        f"{organisation.name}\t{r.full_name}\t{r.email}"
        for organisation in organisations
        for r in organisation.data_providers
    )
    if not tsv_rows:
        return

    tsv_data = f"organisation-name\tfull-name\temail-address\n{tsv_rows}\n"
    total_providers = sum(len(organisation.data_providers) for organisation in organisations)

    setup_data_providers_page = SetUpDataProvidersPage(page, domain, grant_id, collection_id)
    setup_data_providers_page.navigate()
    setup_data_providers_page.fill_users_tsv_data(tsv_data)
    setup_data_providers_page.set_up_button.click()
    noun = "data provider" if total_providers == 1 else "data providers"
    expect(page.get_by_text(f"Successfully set up {total_providers} grant recipient {noun}.")).to_be_visible()


# --- Tasklist checklist items ----------------------------------------------


def override_certifiers(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    org_name: str,
    data_providers: list[DataProviderConfig],
) -> None:
    """Name data_providers[0] as org_name's certifier, via the "Override certifiers for this grant" page."""
    if not data_providers:
        raise ValueError("override_certifiers requires data_providers")

    override_certifiers_page = OverrideGrantRecipientCertifiersPage(page, domain, grant_id, collection_id)
    override_certifiers_page.navigate()
    override_certifiers_page.select_organisation(org_name)
    override_certifiers_page.complete_user_details(data_providers[0].full_name, data_providers[0].email)
    override_certifiers_page.click_add_certifier()


def set_reporting_and_submission_dates(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    collection_name: str,
) -> None:
    """Set reporting and submission dates to an open window, via their tasklist tasks."""
    tasklist_page = AdminCollectionLifecycleTasklistPage(page, domain, grant_id, collection_id)
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


def mark_as_onboarding(page: Page, domain: str, grant_id: str, collection_id: str) -> None:
    """Move the grant from DRAFT to ONBOARDING, via the "Mark as onboarding with Funding Service" task."""
    tasklist_page = AdminCollectionLifecycleTasklistPage(page, domain, grant_id, collection_id)
    tasklist_page.navigate()
    tasklist_page.click_task("Mark as onboarding with Funding Service")
    mark_as_onboarding_page = MarkAsOnboardingWithFundingServicePage(page, domain, grant_id, collection_id)
    mark_as_onboarding_page.click_mark_as_onboarding()


def set_privacy_policy(page: Page, domain: str, grant_id: str, collection_id: str) -> None:
    """Set a privacy policy, via the "Set privacy policy" task."""
    tasklist_page = AdminCollectionLifecycleTasklistPage(page, domain, grant_id, collection_id)
    tasklist_page.navigate()
    tasklist_page.click_task("Set privacy policy")
    set_privacy_policy_page = SetPrivacyPolicyPage(page, domain, grant_id, collection_id)
    set_privacy_policy_page.fill_privacy_policy_markdown("https://www.gov.uk/help/privacy-notice")
    set_privacy_policy_page.click_save_privacy_policy()


def configure_report_settings(page: Page, domain: str, collection_id: str, collection: CollectionConfig) -> None:
    """Apply collection.allow_validation/turn_off_requires_certification via the report settings task."""
    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    if collection.allow_validation:
        report_settings_page.click_allow_validation()
    if collection.turn_off_requires_certification:
        report_settings_page.click_turn_off_requires_certification()
    report_settings_page.click_save()


# --- Settings-page overrides (bypass the tasklist) --------------------------


def set_grant_and_collection_live(page: Page, domain: str, grant_id: str, collection_id: str) -> None:
    """Directly set the grant to LIVE and the collection to OPEN, via the platform-admin settings pages."""
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status(GrantStatusEnum.LIVE)
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status(CollectionStatusEnum.OPEN)
    report_settings_page.click_save()


def enable_public_sign_up(page: Page, domain: str, grant_id: str, grant_name: str, collection: CollectionConfig) -> str:
    """Turn on public sign up for an application collection, and build its eligibility question."""
    # Local import to avoid a circular import; to be tidied up later.
    from tests.e2e.deliver_grant_funding.test_create_preview_collection import create_question_or_group

    assert collection.eligibility

    pre_award_forms_page = GrantPreAwardFormsPage(page, domain, grant_name)
    pre_award_forms_page.navigate(grant_id)
    manage_collection_page = pre_award_forms_page.click_manage_settings(collection.name)
    public_sign_up_settings_page = manage_collection_page.click_change_public_sign_up()
    public_sign_up_url = public_sign_up_settings_page.get_public_sign_up_url()
    public_sign_up_settings_page.select_allow_public_sign_up(True)
    public_sign_up_settings_page.click_save()

    # Turning on public sign up auto-creates an "Eligibility questions" section.
    form_sections_page = navigate_to_pre_award_sections_page(page, domain, grant_name, collection.name)
    manage_section_page = form_sections_page.click_manage_section("Eligibility questions")
    create_question_or_group(collection.eligibility.question, manage_section_page)

    edit_question_page = manage_section_page.click_edit_question(collection.eligibility.question["text"])
    add_eligibility_page = edit_question_page.click_set_eligibility_condition()
    add_eligibility_page.click_eligible_answer(collection.eligibility.qualifying_answer)
    add_eligibility_page.click_save()

    return public_sign_up_url


# --- Grant team membership ---------------------------------------------------


def invite_and_claim_grant_team_member(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    email: str,
    grant_name: str,
) -> None:
    """Invite the shared grant-team-member identity onto this grant, then log in as them to claim it."""
    # Local imports to avoid circular imports: conftest.py imports from this module, and this module would
    # otherwise need to import from the test file switch_user lives in.
    from tests.e2e.conftest import DeliverGrantFundingUserType, e2e_user_configs
    from tests.e2e.deliver_grant_funding.test_create_preview_collection import switch_user

    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    # Workaround: GrantDashboardBasePage.click_grant_team() clicks the wrong nav link (pre-existing bug);
    # click the correct one directly instead.
    grant_dashboard_page.grant_team_nav.click()
    grant_team_member_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    grant_team_page = GrantTeamPage(page, domain)
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    add_grant_team_member_page.fill_in_user_email(grant_team_member_email)
    add_grant_team_member_page.click_continue()

    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_member_email)
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)


# --- Navigation utilities -----------------------------------------------------


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
    """Navigate to a report collection's "manage sections" page."""
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)
    report_sections_page = grant_reports_page.click_manage_sections(grant_name=grant_name, report_name=report_name)
    return report_sections_page


def navigate_to_pre_award_sections_page(
    page: Page, domain: str, grant_name: str, form_name: str
) -> PreAwardFormSectionsPage:
    """Navigate to an application collection's "manage sections" page."""
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(grant_name)
    grant_pre_award_forms_page = grant_dashboard_page.click_pre_award(grant_name)
    form_sections_page = grant_pre_award_forms_page.click_manage_sections(grant_name=grant_name, form_name=form_name)
    return form_sections_page


def _add_sections(
    page: Page,
    domain: str,
    sections: list[SectionDict],
    grant_name: str,
    collection_name: str,
    list_page: GrantReportsPage | GrantPreAwardFormsPage,
) -> None:
    """Add each section (and its questions) to a report or application collection."""
    # Local import to avoid a circular import; to be tidied up later.
    from tests.e2e.deliver_grant_funding.test_create_preview_collection import create_question_or_group

    is_report = isinstance(list_page, GrantReportsPage)

    for i, section in enumerate(sections):
        if i == 0:
            add_section_page = list_page.click_add_section(collection_name, grant_name)
        else:
            sections_page = (
                navigate_to_report_sections_page(page, domain, grant_name, collection_name)
                if is_report
                else navigate_to_pre_award_sections_page(page, domain, grant_name, collection_name)
            )
            add_section_page = sections_page.click_add_section()
        add_section_page.fill_in_section_name(section["name"])
        sections_page = add_section_page.click_add_section()
        manage_section_page = sections_page.click_manage_section(section["name"])
        for component in section["components"]:
            create_question_or_group(component, manage_section_page)
