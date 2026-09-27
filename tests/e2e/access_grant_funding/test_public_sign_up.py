import uuid

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import CollectionStatusEnum, GrantStatusEnum, QuestionDataType
from tests.e2e.access_grant_funding.pages import (
    AccessGrantPage,
    AlreadyApplyingPage,
    CreateOrganisationAllowTeamMembersPage,
    CreateOrganisationCheckYourAnswersPage,
    CreateOrganisationNamePage,
    CreateOrganisationTypePage,
    CreateOrganisationUserNamePage,
    EligibleToApplyPage,
    OrganisationAlreadyExistsPage,
    PublicSignUpEligibilityQuestionPage,
    PublicSignUpIneligiblePage,
    PublicSignUpStartPage,
    RequestALinkToSignInPage,
)
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser, QuestionDict, QuestionResponse
from tests.e2e.deliver_grant_funding.helpers import (
    create_grant,
    extract_uuid_from_url,
    navigate_to_pre_award_sections_page,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    GrantPreAwardFormsPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    RunnerTasklistPage,
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import (
    complete_task,
    create_question_or_group,
    task_check_your_answers,
)
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
    delete_organisation_through_admin,
    retrieve_magic_link,
)

COLLECTION_NAME = f"Public sign up round {uuid.uuid4()}"
APPLICATION_SECTION_NAME = "Section 1"
ELIGIBILITY_SECTION_NAME = "Eligibility questions"

# Fixed, reusable, non-internal users for public sign up tests
USER_1_EMAIL = "fs-e2e-public-sign-up-1@levellingup.gov.uk"
USER_2_EMAIL = "fs-e2e-public-sign-up-2@levellingup.gov.uk"

application_question: QuestionDict = QuestionDict(
    {
        "type": QuestionDataType.TEXT_SINGLE_LINE,
        "text": "What is your project called?",
        "display_text": "What is your project called?",
        "answers": [QuestionResponse("Test Project")],
    }
)

eligibility_question: QuestionDict = QuestionDict(
    {
        "type": QuestionDataType.YES_NO,
        "text": "Is your organisation based in the UK?",
        "display_text": "Is your organisation based in the UK?",
        "answers": [QuestionResponse("Yes")],
    }
)

# Module-level storage for shared test data across dependent tests
_shared_setup_data: dict | None = None


def start_public_sign_up_and_claim_magic_link(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, public_sign_up_url: str, email: str
) -> None:
    page.goto(public_sign_up_url)
    start_page = PublicSignUpStartPage(page, domain)
    expect(start_page.start_now_button).to_be_visible()
    request_a_link_page = start_page.click_start_now()

    request_a_link_page.fill_email_address(email)
    request_a_link_page.click_continue()

    claim_magic_link_from_notification(page, e2e_test_secrets)


def claim_magic_link_from_notification(page: Page, e2e_test_secrets: EndToEndTestSecrets) -> None:
    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id

    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)


def handle_optional_user_name_step(page: Page, domain: str, name: str, next_heading_name: str) -> None:
    """The "what is your full name?" step only appears the first time a given user ever completes a public sign
    up - once the name is set on that first run, it's never asked again."""
    user_name_page = CreateOrganisationUserNamePage(page, domain)
    next_page_heading = page.get_by_role("heading", name=next_heading_name)
    expect(user_name_page.heading.or_(next_page_heading)).to_be_visible()
    if user_name_page.heading.is_visible():
        user_name_page.fill_user_name(name)
        user_name_page.click_continue()


def test_public_sign_up_setup(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> None:
    """Setup test: creates a grant and an application collection with public sign up enabled, with a single
    yes/no eligibility question where 'Yes' is the qualifying answer."""
    global _shared_setup_data

    grant_name_uuid = str(uuid.uuid4())
    grant_name = f"E2E public sign up {grant_name_uuid}"

    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    create_grant(grant_name, grant_name_uuid, all_grants_page)
    grant_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")

    pre_award_forms_page = GrantPreAwardFormsPage(page, domain, grant_name)
    pre_award_forms_page.navigate(grant_id)
    method_page = pre_award_forms_page.click_add_form()
    add_form_page = method_page.click_create_new()
    add_form_page.fill_in_form_name(COLLECTION_NAME)
    pre_award_forms_page = add_form_page.click_submit(grant_name)

    # Add a section with a single question to the application form
    add_section_page = pre_award_forms_page.click_add_section(COLLECTION_NAME, grant_name)
    add_section_page.fill_in_section_name(APPLICATION_SECTION_NAME)
    form_sections_page = add_section_page.click_add_section()
    manage_section_page = form_sections_page.click_manage_section(APPLICATION_SECTION_NAME)
    create_question_or_group(application_question, manage_section_page)

    # Turn on public sign up - this auto-creates the "Eligibility questions" section
    pre_award_forms_page.navigate(grant_id)
    manage_collection_page = pre_award_forms_page.click_manage_settings(COLLECTION_NAME)
    collection_id = extract_uuid_from_url(page.url, r"/applications/(?P<uuid>[a-f0-9-]+)")
    public_sign_up_settings_page = manage_collection_page.click_change_public_sign_up()
    public_sign_up_url = public_sign_up_settings_page.get_public_sign_up_url()
    public_sign_up_settings_page.select_allow_public_sign_up(True)
    public_sign_up_settings_page.click_save()

    # Add the eligibility question, and set "Yes" as the qualifying answer
    form_sections_page = navigate_to_pre_award_sections_page(page, domain, grant_name, COLLECTION_NAME)
    manage_section_page = form_sections_page.click_manage_section(ELIGIBILITY_SECTION_NAME)
    create_question_or_group(eligibility_question, manage_section_page)

    edit_question_page = manage_section_page.click_edit_question(eligibility_question["text"])
    add_eligibility_page = edit_question_page.click_set_eligibility_condition()
    add_eligibility_page.click_eligible_answer("Yes")
    add_eligibility_page.click_save()

    # Make the grant and collection live via admin
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status(GrantStatusEnum.LIVE)
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status(CollectionStatusEnum.OPEN)
    report_settings_page.click_save()

    # Set up a second grant, copying the form so a domain-matched user can successfully join an
    # organisation on a grant it hasn't applied to yet, rather than always hitting "already applying"
    grant_2_name_uuid = str(uuid.uuid4())
    grant_2_name = f"E2E public sign up 2 {grant_2_name_uuid}"

    all_grants_page.navigate()
    create_grant(grant_2_name, grant_2_name_uuid, all_grants_page)
    grant_2_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")

    pre_award_forms_page_2 = GrantPreAwardFormsPage(page, domain, grant_2_name)
    pre_award_forms_page_2.navigate(grant_2_id)
    method_page_2 = pre_award_forms_page_2.click_add_form()
    select_form_to_copy_page = method_page_2.click_copy_existing()
    select_form_to_copy_page.select_form(COLLECTION_NAME)
    add_form_page_2 = select_form_to_copy_page.click_continue()
    add_form_page_2.fill_in_form_name(COLLECTION_NAME)
    pre_award_forms_page_2 = add_form_page_2.click_submit(grant_2_name)

    pre_award_forms_page_2.click_manage_sections(COLLECTION_NAME, grant_2_name)
    collection_2_id = extract_uuid_from_url(page.url, r"/applications/(?P<uuid>[a-f0-9-]+)")

    # Public sign up carries over from the copy, but we re-save it to be explicit and grab its URL
    pre_award_forms_page_2.navigate(grant_2_id)
    manage_collection_page_2 = pre_award_forms_page_2.click_manage_settings(COLLECTION_NAME)
    public_sign_up_settings_page_2 = manage_collection_page_2.click_change_public_sign_up()
    public_sign_up_url_2 = public_sign_up_settings_page_2.get_public_sign_up_url()
    public_sign_up_settings_page_2.select_allow_public_sign_up(True)
    public_sign_up_settings_page_2.click_save()

    grant_settings_page_2 = PlatformAdminGrantSettingsPage(page, domain, grant_2_id)
    grant_settings_page_2.navigate()
    grant_settings_page_2.select_grant_status(GrantStatusEnum.LIVE)
    grant_settings_page_2.click_save()

    report_settings_page_2 = PlatformAdminReportSettingsPage(page, domain, collection_2_id)
    report_settings_page_2.navigate()
    report_settings_page_2.select_collection_status(CollectionStatusEnum.OPEN)
    report_settings_page_2.click_save()

    _shared_setup_data = {
        "grant_name": grant_name,
        "grant_name_uuid": grant_name_uuid,
        "grant_id": grant_id,
        "collection_id": collection_id,
        "public_sign_up_url": public_sign_up_url,
        "grant_2_name": grant_2_name,
        "grant_2_name_uuid": grant_2_name_uuid,
        "grant_2_id": grant_2_id,
        "collection_2_id": collection_2_id,
        "public_sign_up_url_2": public_sign_up_url_2,
    }


def test_public_sign_up_new_organisation_leaves_application_not_started(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets
) -> None:
    """A member of the public with no existing organisation match starts a public sign up, signs in via a magic
    link, answers the eligibility question (including a wrong answer that's corrected after hitting the
    ineligible page), and creates a new organisation with domain sign up enabled - leaving the application not
    started so a second user from the same organisation can be tested before it's filled in."""
    global _shared_setup_data
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    start_public_sign_up_and_claim_magic_link(page, domain, e2e_test_secrets, data["public_sign_up_url"], USER_1_EMAIL)

    # Answer No first, and hit the ineligible page
    question_page = PublicSignUpEligibilityQuestionPage(page, domain, eligibility_question["text"])
    expect(question_page.heading).to_be_visible()
    question_page.click_no()
    question_page.click_continue()

    ineligible_page = PublicSignUpIneligiblePage(page, domain)
    expect(ineligible_page.heading).to_be_visible()
    ineligible_page.click_back()

    # Back on the question: answer Yes this time
    question_page = PublicSignUpEligibilityQuestionPage(page, domain, eligibility_question["text"])
    expect(question_page.heading).to_be_visible()
    question_page.click_yes()
    question_page.click_continue()

    # No matched organisation, so we create one, allowing anyone with our email domain to sign up in future
    eligible_to_apply_page = EligibleToApplyPage(page, domain)
    expect(eligible_to_apply_page.heading).to_be_visible()
    eligible_to_apply_page.click_create_an_organisation()

    org_name = f"E2E Public Sign Up Org {uuid.uuid4()}"

    org_type_page = CreateOrganisationTypePage(page, domain)
    expect(org_type_page.heading).to_be_visible()
    org_type_page.select_other()
    org_type_page.click_continue()

    org_name_page = CreateOrganisationNamePage(page, domain)
    expect(org_name_page.heading).to_be_visible()
    org_name_page.fill_name(org_name)
    org_name_page.click_continue()

    allow_team_members_page = CreateOrganisationAllowTeamMembersPage(page, domain)
    allow_team_members_page.click_yes()
    allow_team_members_page.click_continue()

    handle_optional_user_name_step(
        page, domain, "E2E Test Applicant One", next_heading_name="Confirm your details are correct"
    )

    check_your_answers_page = CreateOrganisationCheckYourAnswersPage(page, domain)
    expect(check_your_answers_page.heading).to_be_visible()
    check_your_answers_page.click_confirm()

    # Lands back on the applicant's list of forms, with a success banner confirming the new organisation
    expect(page.get_by_role("heading", name="Organisation created")).to_be_visible()
    expect(
        page.get_by_text(f"{org_name} has been created successfully. You can now start applying for")
    ).to_be_visible()

    # Stop here with the application not started, so a second user from the same organisation can hit the
    # "already applying" page before we come back, fill it in and submit it
    grant_page = AccessGrantPage(page, domain)
    grant_page.click_collection(COLLECTION_NAME)

    tasklist_page = RunnerTasklistPage(page, domain, data["grant_name"], COLLECTION_NAME)
    expect(tasklist_page.heading).to_be_visible()
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()

    _shared_setup_data = {
        **data,
        "org_name": org_name,
    }


def test_public_sign_up_second_user_same_domain_hits_already_applying(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets
) -> None:
    """A second member of the public, sharing the same email domain as the organisation set up in the previous
    test, is matched to that organisation but finds someone is already applying on its behalf for the first
    grant. Trying to create a new organisation with the same name instead is also rejected. Applying to a second
    grant the organisation hasn't touched yet succeeds instead."""
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    start_public_sign_up_and_claim_magic_link(page, domain, e2e_test_secrets, data["public_sign_up_url"], USER_2_EMAIL)

    question_page = PublicSignUpEligibilityQuestionPage(page, domain, eligibility_question["text"])
    expect(question_page.heading).to_be_visible()
    question_page.click_yes()
    question_page.click_continue()

    eligible_to_apply_page = EligibleToApplyPage(page, domain)
    expect(eligible_to_apply_page.heading).to_be_visible()
    eligible_to_apply_page.select_organisation(data["org_name"])
    eligible_to_apply_page.click_continue()

    already_applying_page = AlreadyApplyingPage(page, domain)
    expect(already_applying_page.heading).to_be_visible()
    already_applying_page.click_back()

    # Instead of applying on behalf of the matched organisation, try to create a new one with already existing name
    eligible_to_apply_page.select_organisation("Apply on behalf of another organisation")
    eligible_to_apply_page.click_continue()

    org_type_page = CreateOrganisationTypePage(page, domain)
    expect(org_type_page.heading).to_be_visible()
    org_type_page.select_other()
    org_type_page.click_continue()

    org_name_page = CreateOrganisationNamePage(page, domain)
    expect(org_name_page.heading).to_be_visible()
    org_name_page.fill_name(data["org_name"])
    org_name_page.click_continue()

    organisation_already_exists_page = OrganisationAlreadyExistsPage(page, domain)
    expect(organisation_already_exists_page.heading).to_be_visible()

    # Still the same (already authenticated) user - applying to a second grant that the organisation hasn't
    # applied to yet should succeed, rather than hitting "already applying" again
    page.goto(data["public_sign_up_url_2"])
    start_page_2 = PublicSignUpStartPage(page, domain)
    expect(start_page_2.start_now_button).to_be_visible()
    # Being already authenticated skips the magic link step entirely, straight through to eligibility questions
    start_page_2.start_now_button.click()

    question_page_2 = PublicSignUpEligibilityQuestionPage(page, domain, eligibility_question["text"])
    expect(question_page_2.heading).to_be_visible()
    question_page_2.click_yes()
    question_page_2.click_continue()

    eligible_to_apply_page_2 = EligibleToApplyPage(page, domain)
    expect(eligible_to_apply_page_2.heading).to_be_visible()
    eligible_to_apply_page_2.select_organisation(data["org_name"])
    eligible_to_apply_page_2.click_continue()

    handle_optional_user_name_step(page, domain, "E2E Test Applicant Two", next_heading_name="Added to organisation")

    expect(page.get_by_role("heading", name="Added to organisation")).to_be_visible()
    expect(page.get_by_text(f"You've been added to {data['org_name']}. You can now apply for")).to_be_visible()


def test_public_sign_up_first_user_resumes_and_submits(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets
) -> None:
    """The original applicant signs back in and fills in and submits the application they left not started."""
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    request_a_link_page.fill_email_address(USER_1_EMAIL)
    request_a_link_page.click_request_a_link()
    claim_magic_link_from_notification(page, e2e_test_secrets)

    grant_page = AccessGrantPage(page, domain)
    grant_page.click_collection(COLLECTION_NAME)

    tasklist_page = RunnerTasklistPage(page, domain, data["grant_name"], COLLECTION_NAME)
    expect(tasklist_page.heading).to_be_visible()
    complete_task(tasklist_page, APPLICATION_SECTION_NAME, data["grant_name"], [application_question])
    task_check_your_answers(tasklist_page, data["grant_name"], COLLECTION_NAME, [application_question])

    confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
    confirmation_page = confirm_submit_page.click_confirm_and_submit()
    expect(confirmation_page.heading).to_be_visible()


def test_public_sign_up_cleanup(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email: str,
) -> None:
    """Tidy up the grant, organisation and grant recipient created during this journey."""
    if _shared_setup_data is None:
        pytest.skip("No setup data to clean up")

    delete_grant_recipient_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
    delete_grant_recipient_through_admin(page, domain, _shared_setup_data["grant_2_name_uuid"])
    delete_organisation_through_admin(page, domain, _shared_setup_data["org_name"])
    delete_grant_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
    delete_grant_through_admin(page, domain, _shared_setup_data["grant_2_name_uuid"])
