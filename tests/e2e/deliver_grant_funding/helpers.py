from decimal import Decimal

from playwright.sync_api import Locator, Page, expect

from app import NumberTypeEnum
from app.common.data.types import (
    CollectionStatusEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    GroupDisplayOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import ManagedExpression
from app.common.filters import format_thousands
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import (
    CollectionConfig,
    DataProviderConfig,
    E2EManagedExpression,
    OrganisationConfig,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    SectionDict,
    TQuestionToTest,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDashboardPage, GrantTeamPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AddConditionPage,
    AddQuestionDetailsPage,
    AdminCollectionLifecycleTasklistPage,
    CreateCalculatedConditionPage,
    CreateCustomExpressionPage,
    EditQuestionGroupPage,
    EditQuestionPage,
    GrantPreAwardFormsPage,
    GrantReportsPage,
    ManageSectionPage,
    MarkAsOnboardingWithFundingServicePage,
    OrganisationSetupRow,
    OverrideGrantRecipientCertifiersPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    PreAwardFormSectionsPage,
    ReportSectionsPage,
    RunnerCheckYourAnswersPage,
    RunnerQuestionPage,
    RunnerTasklistPage,
    SetPrivacyPolicyPage,
    SetReportingDatesPage,
    SetSubmissionDatesPage,
    SetUpDataProvidersPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
    reference_data_flow,
)
from tests.e2e.helpers import extract_uuid_from_url, wait_for_context_aware_textarea_to_be_ready

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
    # Local import to avoid a circular import: conftest.py imports from this module at the top level, so this
    # module can't import from conftest.py at the top level too.
    from tests.e2e.conftest import DeliverGrantFundingUserType, e2e_user_configs, switch_user

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


# --- Question-building helpers ----------------------------------------------


def create_question_or_group(
    question_definition: TQuestionToTest,
    manage_section_page: ManageSectionPage | EditQuestionGroupPage,
    parent_group_name: str | None = None,
    parent_add_another: bool = False,
):
    if question_definition["type"] == "group":
        add_question_group_page = manage_section_page.click_add_question_group(question_definition["text"])
        add_question_group_page.fill_in_question_group_name()
        group_display_options_page = add_question_group_page.click_continue()
        group_display_options_page.click_question_group_display_type(question_definition["display_options"])

        if parent_add_another:
            assert parent_group_name is not None, "parent_add_another requires a parent_group_name"
            edit_question_group_page = group_display_options_page.click_submit_nested(parent_group_name)
        else:
            add_another_options_page = group_display_options_page.click_submit()
            add_another_options_page.click_add_another(question_definition.get("add_another", False))
            edit_question_group_page = add_another_options_page.click_submit(parent_group_name)
        if (
            question_definition.get("guidance") is not None
            and question_definition.get("display_options") == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        ):
            add_question_guidance(question_definition, edit_question_group_page)
        if question_definition.get("condition") is not None:
            add_condition(edit_question_group_page, question_definition["condition"])
        for question in question_definition["questions"]:
            create_question_or_group(
                question,
                edit_question_group_page,
                parent_group_name=question_definition["text"],
                parent_add_another=question_definition.get("add_another", False),
            )
        if question_definition.get("validation") is not None:
            add_group_validation(edit_question_group_page, question_definition["validation"])
        if parent_group_name:
            edit_question_group_page.click_parent_group_breadcrumb()
        else:
            edit_question_group_page.click_section_breadcrumb()
    else:
        create_question(question_definition, manage_section_page, parent_group_name=parent_group_name)


def _assert_reports_breadcrumb_layout(page: Page, parent_group_name: str | None = None) -> None:
    breadcrumbs = page.locator("a.govuk-breadcrumbs__link")
    if not parent_group_name:
        expect(breadcrumbs).to_have_count(3)
        expect(page.get_by_text("question group hidden ...")).not_to_be_visible()
    elif parent_group_name == "This is a question group" or parent_group_name == "One question per page group":
        expect(breadcrumbs).to_have_count(4)
        expect(page.get_by_text("question group hidden ...")).not_to_be_visible()
    elif parent_group_name == "Nested Group":
        expect(breadcrumbs).to_have_count(4)
        expect(page.get_by_text("question group hidden ...")).to_be_visible()


def create_question(
    question_definition: QuestionDict,
    manage_page: ManageSectionPage | EditQuestionGroupPage,
    parent_group_name: str | None = None,
) -> None:
    question_type_page = manage_page.click_add_question()
    question_type_page.click_question_type(question_definition["type"])
    question_details_page = question_type_page.click_continue()

    expect(question_details_page.page.get_by_text(question_definition["type"].value, exact=True)).to_be_visible()
    question_text = question_definition["text"]
    wait_for_context_aware_textarea_to_be_ready(question_details_page.page, "text")
    wait_for_context_aware_textarea_to_be_ready(question_details_page.page, "hint")

    if question_definition["type"] == QuestionDataType.NUMBER:
        data_options = question_definition["data_options"]
        assert data_options.number_type is not None
        question_details_page.select_number_type(data_options.number_type)
        if data_options.number_type == NumberTypeEnum.DECIMAL:
            assert data_options.max_decimal_places is not None
            question_details_page.fill_max_number_of_decimal_places(data_options.max_decimal_places)

    question_details_page.fill_question_text(question_text)
    question_details_page.fill_question_name(question_text.lower())

    if text_reference := question_definition.get("text_reference"):
        select_data_source_page = question_details_page.click_insert_data(field_name="text")
        reference_data_flow(select_data_source_page, text_reference)

    if hint := question_definition.get("hint"):
        question_details_page.fill_question_hint(hint.prefix)
        select_data_source_page = question_details_page.click_insert_data(field_name="hint")
        reference_data_flow(select_data_source_page, hint.data_reference)
    else:
        question_details_page.fill_question_hint(f"Hint text for: {question_text}")

    if question_definition["type"] in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
        question_details_page.fill_data_source_items(question_definition["choices"])

        options = question_definition.get("options")
        if options is not None and options.last_data_source_item_is_distinct_from_others is not None:
            question_details_page.click_other_option_checkbox()
            question_details_page.enter_other_option_text()

    if (
        question_definition["type"]
        in [QuestionDataType.NUMBER, QuestionDataType.TEXT_MULTI_LINE, QuestionDataType.DATE]
        and question_definition.get("options") is not None
    ):
        add_advanced_formatting(question_definition, question_details_page)

    edit_question_page = question_details_page.click_submit()

    _assert_reports_breadcrumb_layout(edit_question_page.page, parent_group_name=parent_group_name)

    if question_definition.get("guidance") is not None:
        add_question_guidance(question_definition, edit_question_page)
    if question_definition.get("validation") is not None:
        add_validation(
            edit_question_page,
            question_definition["validation"],
            question_definition.get("options", None),
        )
    if question_definition.get("condition") is not None:
        add_condition(edit_question_page, question_definition["condition"], question_definition.get("options", None))

    if isinstance(manage_page, EditQuestionGroupPage):
        edit_question_page.click_question_group_breadcrumb(manage_page.group_name)
    else:
        edit_question_page.click_section_breadcrumb()


def add_advanced_formatting(question_definition: QuestionDict, question_details_page: AddQuestionDetailsPage) -> None:
    options = question_definition.get("options")
    assert options is not None
    question_details_page.click_advanced_formatting_options()
    match question_definition["type"]:
        case QuestionDataType.TEXT_MULTI_LINE:
            if options.rows is not None:
                question_details_page.select_multiline_input_rows(options.rows)
            if options.word_limit is not None:
                question_details_page.fill_word_limit(options.word_limit)
        case QuestionDataType.NUMBER:
            if options.prefix is not None:
                question_details_page.fill_prefix(options.prefix)
            if options.suffix is not None:
                question_details_page.fill_suffix(options.suffix)
            if options.width is not None:
                question_details_page.select_input_width(options.width)
        case QuestionDataType.DATE:
            if options.approximate_date is True:
                question_details_page.click_is_approximate_date_checkbox()
        case _:
            pass  # No advanced formatting for other question types


def add_question_guidance(
    question_definition: TQuestionToTest, edit_question_page: EditQuestionPage | EditQuestionGroupPage
) -> None:
    guidance = question_definition.get("guidance")
    if guidance is not None:
        add_guidance_page = edit_question_page.click_add_guidance()
        add_guidance_page.fill_guidance_heading(guidance.heading)
        wait_for_context_aware_textarea_to_be_ready(add_guidance_page.page, "guidance_body")
        add_guidance_page.fill_guidance_default()
        edit_question_page = add_guidance_page.click_save_guidance_button(edit_question_page)
        expect(edit_question_page.page.get_by_text("Page heading", exact=True)).to_be_visible()
        expect(edit_question_page.page.get_by_text("Guidance text", exact=True)).to_be_visible()
        edit_question_page.click_change_guidance()
        add_guidance_page.fill_guidance(guidance)
        add_guidance_page.click_save_guidance_button(edit_question_page)


def add_group_validation(
    edit_question_group_page: EditQuestionGroupPage,
    validation: E2EManagedExpression,
) -> None:
    # Group validation only supports custom (calculated) expressions, never managed ones.
    assert isinstance(validation.evaluatable_expression, CustomExpression)
    assert validation.evaluatable_expression.custom_message is not None
    assert validation.expression_references is not None

    add_validation_page = edit_question_group_page.click_add_validation()
    add_validation_page.configure_custom_expression(
        validation.evaluatable_expression.custom_expression, validation.expression_references
    )
    add_validation_page.configure_custom_message(
        validation.evaluatable_expression.custom_message, validation.expression_references
    )
    add_validation_page.click_create_group_validation_expression()


def add_validation(
    edit_question_page: EditQuestionPage,
    validation: E2EManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    add_validation_page = edit_question_page.click_add_validation()
    if isinstance(validation.evaluatable_expression, CustomExpression):
        add_validation_page.click_calculation_option()
        add_custom_validation_page = add_validation_page.click_add_validation()
        assert isinstance(add_custom_validation_page, CreateCustomExpressionPage)
        assert validation.expression_references is not None

        add_custom_validation_page.configure_custom_expression(
            validation.evaluatable_expression.custom_expression, validation.expression_references
        )
        add_custom_validation_page.configure_custom_message(
            validation.evaluatable_expression.custom_message, validation.expression_references
        )
        add_custom_validation_page.click_create_custom_validation_expression()

    else:
        assert isinstance(validation.evaluatable_expression, ManagedExpression)
        add_validation_page.configure_managed_validation(
            validation.evaluatable_expression, validation.context_source, presentation_options
        )
        add_validation_page.click_add_validation()


def add_condition(
    edit_question_page: EditQuestionPage | EditQuestionGroupPage,
    condition: E2EManagedExpression,
    presentation_options: QuestionPresentationOptions | None = None,
) -> None:
    select_calculation_page = edit_question_page.click_add_condition()
    if isinstance(condition.evaluatable_expression, CustomExpression):
        assert condition.evaluatable_expression.expression_name is not None
        assert condition.expression_references is not None
        select_calculation_page.click_yes_need_calculation()
        calculated_condition_page = select_calculation_page.click_continue()
        assert isinstance(calculated_condition_page, CreateCalculatedConditionPage)
        calculated_condition_page.fill_calculation_name(condition.evaluatable_expression.expression_name)
        calculated_condition_page.configure_custom_expression(
            expression=condition.evaluatable_expression.custom_expression,
            expression_references=condition.expression_references,
        )
        calculated_condition_page.click_create_calculated_condition(edit_question_page)
    else:
        assert condition.conditional_on is not None
        select_calculation_page.click_no_calculation()
        add_condition_page = select_calculation_page.click_continue()
        assert isinstance(add_condition_page, AddConditionPage)
        assert isinstance(condition.evaluatable_expression, ManagedExpression)
        select_data_source_page = add_condition_page.click_reference_data_button()
        reference_data_flow(select_data_source_page, condition.conditional_on)
        add_condition_page.configure_managed_condition(
            condition.evaluatable_expression, condition.context_source, presentation_options
        )
        add_condition_page.click_add_condition(edit_question_page)


def answer_questions_and_check_for_expected_errors(
    questions_on_this_page: list[QuestionDict],
    question_page: RunnerQuestionPage,
    group_validation_error: str | None = None,
    same_page_group: bool = False,
):
    for question in questions_on_this_page:
        question_page = RunnerQuestionPage(
            question_page.page,
            question_page.domain,
            question_page.grant_name,
            question["text"],
            is_in_a_same_page_group=same_page_group,
        )
        assert_question_visibility(question_page, question)

    max_answers = max(len(q["answers"]) for q in questions_on_this_page)
    for answer_idx in range(max_answers):
        expect_errors = False
        current_responses: list[QuestionResponse] = []
        for question in questions_on_this_page:
            if "This question should not be shown" in question["display_text"]:
                continue

            # If this question doesn't have as many answers as other questions in the group, just use its last answer
            response = (
                question["answers"][answer_idx]
                if answer_idx < len(question["answers"])
                else question["answers"][len(question["answers"]) - 1]
            )
            current_responses.append(response)
            if response.error_message or response.expect_group_validation_error:
                expect_errors = True
            question_page.respond_to_question(
                question["type"], question.get("display_text", question["text"]), response.answer
            )
        question_page.click_continue()
        if expect_errors:
            for response in current_responses:
                if response.error_message is not None:
                    expect(question_page.page.get_by_role("link", name=response.error_message)).to_be_visible()
                if response.expect_group_validation_error and group_validation_error is not None:
                    expect(question_page.page.get_by_text(group_validation_error)).to_be_visible()


def complete_question_group(
    question_page: RunnerQuestionPage,
    tasklist_page: RunnerTasklistPage,
    grant_name: str,
    group_to_test: QuestionGroupDict,
):
    if group_to_test["display_options"] == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE:
        if group_to_test.get("guidance") is not None:
            # Just checks the guidance for this group is visible
            assert_question_visibility(question_page, group_to_test)

        group_validation = group_to_test.get("validation")
        group_validation_error = None
        if group_validation is not None:
            # Group validation only supports custom (calculated) expressions, never managed ones.
            assert isinstance(group_validation.evaluatable_expression, CustomExpression)
            group_validation_error = group_validation.evaluatable_expression.custom_message

        # Questions directly inside a same-page group are never themselves groups.
        questions_on_this_page: list[QuestionDict] = []
        for nested_question in group_to_test["questions"]:
            assert nested_question["type"] != "group"
            questions_on_this_page.append(nested_question)

        answer_questions_and_check_for_expected_errors(
            questions_on_this_page,
            question_page,
            group_validation_error,
            same_page_group=True,
        )

    else:
        for nested_question in group_to_test["questions"]:
            if nested_question["type"] == "group":
                complete_question_group(question_page, tasklist_page, grant_name, nested_question)
            else:
                answer_questions_and_check_for_expected_errors(
                    [nested_question],
                    question_page,
                    None,
                )


def complete_task(
    tasklist_page: RunnerTasklistPage, section_name: str, grant_name: str, questions_to_test: list[TQuestionToTest]
) -> None:
    tasklist_page.click_on_section(section_name=section_name)
    for question_to_test in questions_to_test:
        question_page = RunnerQuestionPage(
            tasklist_page.page,
            tasklist_page.domain,
            grant_name,
            question_to_test.get("display_text", question_to_test["text"]),
        )

        if question_to_test["type"] == "group":
            complete_question_group(question_page, tasklist_page, grant_name, question_to_test)
        else:
            answer_questions_and_check_for_expected_errors([question_to_test], question_page, None)


def task_check_your_answers(
    tasklist_page: RunnerTasklistPage, grant_name: str, report_name: str, questions_to_test: list[TQuestionToTest]
):
    check_your_answers_page = RunnerCheckYourAnswersPage(tasklist_page.page, tasklist_page.domain, grant_name)

    def _assert_check_your_answers(questions_to_check: list[TQuestionToTest]):
        for question_to_check in questions_to_check:
            if question_to_check["type"] == "group":
                _assert_check_your_answers(question_to_check["questions"])
            else:
                assert_check_your_answers(check_your_answers_page, question_to_check)

    _assert_check_your_answers(questions_to_test)

    expect(check_your_answers_page.page.get_by_text("Have you completed this section?", exact=True)).to_be_visible()

    check_your_answers_page.click_mark_as_complete_yes()
    tasklist_page = check_your_answers_page.click_save_and_continue(report_name=report_name)


def assert_question_visibility(question_page: RunnerQuestionPage, question_to_test: TQuestionToTest) -> None:
    if display_hint := question_to_test.get("display_hint"):
        expect(question_page.page.locator(".govuk-hint", has_text=display_hint)).to_be_visible()

    if question_to_test.get("guidance") is None:
        if "This question should not be shown" in question_to_test["text"]:
            expect(question_page.heading).not_to_be_visible()
        else:
            expect(question_page.heading).to_be_visible()
    else:
        expect(question_page.page.get_by_role("heading", name=question_to_test["guidance"].heading)).to_be_visible()
        expect(
            question_page.page.get_by_role("heading", name=question_to_test["guidance"].body_heading)
        ).to_be_visible()
        expect(question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)).to_be_visible()
        expect(
            question_page.page.get_by_role("link", name=question_to_test["guidance"].body_link_text)
        ).to_have_attribute("href", question_to_test["guidance"].body_link_url)
        for item in question_to_test["guidance"].body_ul_items:
            expect(question_page.page.locator("ul").get_by_text(item)).to_be_visible()
        for item in question_to_test["guidance"].body_ol_items:
            expect(question_page.page.locator("ol").get_by_text(item)).to_be_visible()


def assert_check_your_answers(check_your_answers_page: RunnerCheckYourAnswersPage, question: QuestionDict) -> None:
    if "This question should not be shown" in question["text"]:
        return

    question_heading = check_your_answers_page.page.get_by_text(question["display_text"], exact=True)
    expect(question_heading).to_be_visible()

    question_name = question["text"].lower()
    answer = question["answers"][-1].answer
    if question["type"] == QuestionDataType.CHECKBOXES:
        checkbox_answers_list = check_your_answers_page.page.get_by_test_id(f"answer-{question_name}").locator("li")
        expect(checkbox_answers_list).to_have_text(answer)
    elif question["type"] == QuestionDataType.NUMBER:
        assert isinstance(answer, str)
        answer_to_format = (
            int(answer) if question["data_options"].number_type == NumberTypeEnum.INTEGER else Decimal(answer)
        )
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            f"{question['options'].prefix or ''}{format_thousands(answer_to_format)}{question['options'].suffix or ''}"
        )
    elif question["type"] == QuestionDataType.DATE:
        check_your_answers_text = question["answers"][-1].check_your_answers_text
        assert check_your_answers_text is not None
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(
            check_your_answers_text
        )
    else:
        expect(check_your_answers_page.page.get_by_test_id(f"answer-{question_name}")).to_have_text(answer)


def assert_check_your_answer_for_all_questions(questions_to_check: list[TQuestionToTest], report_answers_list: Locator):
    for question_to_check in questions_to_check:
        if question_to_check["type"] == "group":
            assert_check_your_answer_for_all_questions(question_to_check["questions"], report_answers_list)
        else:
            assert_check_your_answer_for_question(question_to_check, report_answers_list)


def assert_check_your_answer_for_question(question: QuestionDict, answers_list: Locator) -> None:
    # TODO Can we combine this with the logic in assert_check_your_answers? Feels like duplication
    if "This question should not be shown" in question["text"]:
        return
    answer = question["answers"][-1].answer
    if question["type"] == QuestionDataType.CHECKBOXES:
        expect(answers_list.get_by_text(f"{question['text']} {' '.join(answer)}", exact=True)).to_be_visible()
    elif question["type"] == QuestionDataType.NUMBER:
        assert isinstance(answer, str)
        expect(
            answers_list.get_by_text(
                f"{question['text']} {question['options'].prefix or ''}"
                f"{format_thousands(int(answer))}{question['options'].suffix or ''}",
                exact=True,
            )
        ).to_be_visible()
    elif question["type"] == QuestionDataType.DATE:
        check_your_answers_text = question["answers"][-1].check_your_answers_text
        assert check_your_answers_text is not None
        expect(answers_list.get_by_text(check_your_answers_text, exact=True)).to_be_visible()
    else:
        expect(answers_list.get_by_text(f"{question['text']} {answer}", exact=True)).to_be_visible()
