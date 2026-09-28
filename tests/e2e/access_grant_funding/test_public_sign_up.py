import uuid

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import CollectionStatusEnum, GrantStatusEnum, QuestionDataType
from tests.e2e.access_grant_funding.pages import (
    CreateOrganisationAllowTeamMembersPage,
    CreateOrganisationCheckYourAnswersPage,
    CreateOrganisationNamePage,
    CreateOrganisationTypePage,
    CreateOrganisationUserNamePage,
    EligibleToApplyPage,
    PublicSignUpEligibilityQuestionPage,
    PublicSignUpStartPage,
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
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import create_question_or_group
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
    delete_organisation_through_admin,
    retrieve_magic_link,
)

COLLECTION_NAME = f"Public sign up round {uuid.uuid4()}"
ELIGIBILITY_SECTION_NAME = "Eligibility questions"

# Fixed, reusable, non-internal user for public sign up tests
USER_1_EMAIL = "fs-e2e-public-sign-up-1@levellingup.gov.uk"

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

    # Turn on public sign up - this auto-creates the "Eligibility questions" section
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

    _shared_setup_data = {
        "grant_name": grant_name,
        "grant_name_uuid": grant_name_uuid,
        "grant_id": grant_id,
        "collection_id": collection_id,
        "public_sign_up_url": public_sign_up_url,
    }


def test_public_sign_up_new_organisation(page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets) -> None:
    """A member of the public with no existing organisation match starts a public sign up, signs in via a magic
    link, answers the eligibility question, and creates a new organisation with domain sign up enabled."""
    global _shared_setup_data
    assert _shared_setup_data is not None, "Setup test must run first"
    data = _shared_setup_data

    page.goto(data["public_sign_up_url"])
    start_page = PublicSignUpStartPage(page, domain)
    expect(start_page.start_now_button).to_be_visible()
    request_a_link_page = start_page.click_start_now()

    request_a_link_page.fill_email_address(USER_1_EMAIL)
    request_a_link_page.click_continue()

    notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
    assert notification_id
    magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
    page.goto(magic_link_url)

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

    _shared_setup_data = {
        **data,
        "org_name": org_name,
    }


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
    delete_organisation_through_admin(page, domain, _shared_setup_data["org_name"])
    delete_grant_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
