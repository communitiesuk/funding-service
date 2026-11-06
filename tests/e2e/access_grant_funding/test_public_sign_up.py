import uuid
from typing import Callable

from playwright.sync_api import Page, expect

from app.common.data.types import QuestionDataType
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import DeliverGrantFundingUserType, login_with_session_cookie, login_with_stub_sso
from tests.e2e.dataclasses import GrantScenario, GrantScenarioHandle, QuestionDict, QuestionResponse, SectionDict
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_organisation_through_admin,
    retrieve_magic_link,
)
from tests.e2e.pages.access_pages import (
    AccessGrantPage,
    CreateOrganisationAllowTeamMembersPage,
    CreateOrganisationCheckYourAnswersPage,
    CreateOrganisationNamePage,
    CreateOrganisationTypePage,
    CreateOrganisationUserNamePage,
    EligibleToApplyPage,
    PublicSignUpEligibilityQuestionPage,
    PublicSignUpIneligiblePage,
    PublicSignUpStartPage,
)
from tests.e2e.pages.misc_pages import RunnerTasklistPage
from tests.e2e.question_helpers import complete_task, task_check_your_answers


def test_public_sign_up_journey(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    email: str,
    build_grant_scenario: Callable[..., GrantScenarioHandle],
) -> None:
    """A member of the public with no existing organisation match starts a public sign up, signs in via a magic
    link, answers the eligibility question (including a wrong answer that's corrected after hitting the
    ineligible page), creates a new organisation with domain sign up enabled, and fills in and submits the
    application."""
    application_section_name = "Section 1"
    user_1_email = "fs-e2e-public-sign-up-1@funding-service-e2e.gov.uk"
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

    collection_name = f"E2E public sign up round {uuid.uuid4()}"
    scenario = build_grant_scenario(
        GrantScenario(
            collection_name=collection_name,
            collection_type="application",
            sections=[SectionDict(name=application_section_name, components=[application_question])],
            enable_public_sign_up=True,
            eligibility_question=eligibility_question,
            eligibility_qualifying_answer="Yes",
            set_live=True,
        ),
        sign_out_after=True,
    )
    assert scenario.public_sign_up_url is not None

    org_name: str | None = None
    try:
        page.goto(scenario.public_sign_up_url)
        start_page = PublicSignUpStartPage(page, domain)
        expect(start_page.start_now_button).to_be_visible()
        request_a_link_page = start_page.click_start_now()

        request_a_link_page.fill_email_address(user_1_email)
        request_a_link_page.click_continue()

        notification_id = page.locator("[data-notification-id]").get_attribute("data-notification-id")
        assert notification_id
        magic_link_url = retrieve_magic_link(notification_id, e2e_test_secrets)
        page.goto(magic_link_url)

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

        # The "what is your full name?" step only appears the first time a given user ever completes a public
        # sign up - once the name is set on that first run, it's never asked again.
        user_name_page = CreateOrganisationUserNamePage(page, domain)
        confirm_details_heading = page.get_by_role("heading", name="Confirm your details are correct")
        expect(user_name_page.heading.or_(confirm_details_heading)).to_be_visible()
        if user_name_page.heading.is_visible():
            user_name_page.fill_user_name("E2E Test Applicant One")
            user_name_page.click_continue()

        check_your_answers_page = CreateOrganisationCheckYourAnswersPage(page, domain)
        expect(check_your_answers_page.heading).to_be_visible()
        check_your_answers_page.click_confirm()

        # Lands back on the applicant's list of forms, with a success banner confirming the new organisation
        expect(page.get_by_role("heading", name="Organisation created")).to_be_visible()
        expect(
            page.get_by_text(f"{org_name} has been created successfully. You can now start applying for")
        ).to_be_visible()

        # Fill in and submit the application
        grant_page = AccessGrantPage(page, domain)
        grant_page.click_collection(collection_name)

        tasklist_page = RunnerTasklistPage(page, domain, scenario.grant_name, collection_name)
        expect(tasklist_page.heading).to_be_visible()
        complete_task(tasklist_page, application_section_name, scenario.grant_name, [application_question])
        task_check_your_answers(tasklist_page, scenario.grant_name, collection_name, [application_question])

        confirm_submit_page = tasklist_page.click_submit_for_direct_submission()
        confirmation_page = confirm_submit_page.click_confirm_and_submit()
        expect(confirmation_page.heading).to_be_visible()
    finally:
        # Clean up records created during the test: grant recipient and organisation
        if org_name is not None:
            page.goto(f"{domain}/sign-out")
            if e2e_test_secrets.E2E_ENV == "local":
                login_with_stub_sso(domain, page, email, DeliverGrantFundingUserType.PLATFORM_ADMIN)
            else:
                login_with_session_cookie(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN)
            delete_grant_recipient_through_admin(page, domain, scenario.grant_name_uuid)
            delete_organisation_through_admin(page, domain, org_name)
