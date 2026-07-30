import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.interfaces.collections import (
    get_submissions_by_grant_recipient_collection,
    get_unclaimed_submission_for_user,
)
from app.common.data.interfaces.grant_recipients import get_grant_recipient_or_none
from app.common.data.models import GrantRecipient, Organisation, Submission
from app.common.data.models_user import MagicLink
from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    ExpressionType,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    ManagedExpressionsEnum,
    OrganisationModeEnum,
    OrganisationType,
    QuestionDataType,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.expressions.references import ExpressionReference
from tests.models import _get_grant_managing_organisation
from tests.utils import get_h1_text, page_has_error

TRUSTED_DOMAIN = "barnsley.gov.uk"
APPLICANT_EMAIL = f"chief.cheesemonger@{TRUSTED_DOMAIN}"
UNTRUSTED_EMAIL = "someone@example.com"


@pytest.fixture()
def application(factories):
    """An application that anybody can sign up to, on a grant that has gone live."""
    grant = factories.grant.create(
        name="Cheeseboards in parks", slug="cheeseboards-in-parks", status=GrantStatusEnum.LIVE
    )
    return factories.collection.create(
        grant=grant,
        name="Apply for funding",
        slug="apply-for-funding",
        type=CollectionType.APPLICATION,
        status=CollectionStatusEnum.OPEN,
        allow_public_sign_up=True,
    )


@pytest.fixture()
def application_with_eligibility_check(application, factories, db_session):
    """The `application` fixture, gated behind a single yes/no eligibility question."""
    eligibility_form = factories.form.create(collection=application, title="Eligibility", is_eligibility=True)
    question = factories.question.create(
        form=eligibility_form, text="Are you a registered charity?", data_type=QuestionDataType.YES_NO
    )
    factories.expression.create(
        question=question,
        type_=ExpressionType.ELIGIBILITY,
        context={"subject_reference": ExpressionReference.from_question(question)},
        statement=f"{question.safe_qid} is True",
        managed_name=ManagedExpressionsEnum.IS_YES,
    )

    application.requires_eligibility_check = True
    db_session.commit()

    return application, question


def _answer_eligibility_question(client, application, question, answer="1"):
    return client.post(
        url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            collection_id=application.id,
            question_id=question.id,
        ),
        data={question.safe_qid: answer, "submit": "Continue"},
    )


class TestPublicSignUpStart:
    def test_shows_the_grant_and_deadline(self, anonymous_client, application, factories):
        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start",
                grant_slug="cheeseboards-in-parks",
                collection_slug="apply-for-funding",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Check your eligibility"
        assert "Cheeseboards in parks" in soup.text
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"

    def test_404s_for_the_public_when_the_grant_is_not_live(self, anonymous_client, application, db_session):
        application.grant.status = GrantStatusEnum.DRAFT
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start",
                grant_slug="cheeseboards-in-parks",
                collection_slug="apply-for-funding",
            )
        )

        assert response.status_code == 404

    def test_404s_when_the_collection_does_not_allow_public_sign_up(self, anonymous_client, application, db_session):
        application.allow_public_sign_up = False
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start",
                grant_slug="cheeseboards-in-parks",
                collection_slug="apply-for-funding",
            )
        )

        assert response.status_code == 404

    def test_starting_takes_you_to_the_email_page(self, anonymous_client, application):
        response = anonymous_client.post(
            url_for(
                "access_grant_funding.public_sign_up_start",
                grant_slug="cheeseboards-in-parks",
                collection_slug="apply-for-funding",
            ),
            data={"submit": "Start now"},
        )

        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.public_sign_up_email", collection_id=application.id)


class TestPublicSignUpEmail:
    def test_sends_a_magic_link_that_returns_to_the_eligible_page(
        self, anonymous_client, application, db_session, mock_notification_service_calls
    ):
        response = anonymous_client.post(
            url_for("access_grant_funding.public_sign_up_email", collection_id=application.id),
            data={"email_address": APPLICANT_EMAIL},
        )

        magic_link = db_session.query(MagicLink).filter(MagicLink.email == APPLICANT_EMAIL).one()
        assert magic_link.redirect_to_path == url_for(
            "access_grant_funding.public_sign_up_eligible", collection_id=application.id
        )
        assert response.status_code == 302
        assert response.location == url_for("auth.check_email", magic_link_id=magic_link.id)
        assert len(mock_notification_service_calls) == 1

    def test_rejects_an_email_that_is_not_an_email(self, anonymous_client, application):
        response = anonymous_client.post(
            url_for("access_grant_funding.public_sign_up_email", collection_id=application.id),
            data={"email_address": "not-an-email"},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter an email address in the correct format, like name@example.com")


@pytest.mark.authenticate_as(APPLICANT_EMAIL)
class TestPublicSignUpEligible:
    def test_sends_you_to_register_an_organisation_when_your_domain_is_not_registered(
        self, authenticated_no_role_client, application, factories
    ):
        factories.organisation.create(name="Barnsley Council", trusted_domains=["somewhere-else.gov.uk"])

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_organisation_type", collection_id=application.id
        )

    def test_confirms_eligibility_before_you_register_your_own_organisation(
        self, authenticated_no_role_client, application_with_eligibility_check
    ):
        application, question = application_with_eligibility_check
        _answer_eligibility_question(authenticated_no_role_client, application, question)

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "You are eligible to apply"
        assert soup.find("form").find("button", {"type": "submit"}).text.strip() == "Continue and create an account"
        # they have no organisation yet, so there are no organisation details to confirm
        assert "we think you're applying on behalf of" not in soup.text
        assert soup.select_one(".govuk-back-link")["href"] == url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            collection_id=application.id,
            question_id=question.id,
        )

    def test_continuing_to_create_an_account_takes_you_to_register_an_organisation(
        self, authenticated_no_role_client, application_with_eligibility_check
    ):
        application, question = application_with_eligibility_check
        _answer_eligibility_question(authenticated_no_role_client, application, question)

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id),
            data={"submit": "Continue and create an account"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_organisation_type", collection_id=application.id
        )

    def test_offers_to_start_an_application_for_your_organisation(
        self, authenticated_no_role_client, application, factories
    ):
        factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "You are eligible to apply"
        assert "we think you're applying on behalf of Barnsley Council" in soup.text

    def test_signing_up_starts_the_organisation_applying_and_gives_you_data_provider_access(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id),
            data={"submit": "Continue and start application"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=application.grant_id,
        )

        grant_recipient = get_grant_recipient_or_none(application.grant_id, organisation.id)
        assert grant_recipient is not None
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING

        user = authenticated_no_role_client.user
        db_session.refresh(user)
        assert RoleEnum.DATA_PROVIDER in user.roles[0].permissions

    def test_signing_up_also_sets_up_a_test_grant_recipient_and_grant_team_test_access(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        organisation = factories.organisation.create(
            name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN], with_matching_test_org=True
        )
        team_member = factories.user.create()
        factories.user_role.create(
            user=team_member,
            organisation=_get_grant_managing_organisation(),
            grant=application.grant,
            permissions=[RoleEnum.MEMBER],
        )

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id),
            data={"submit": "Continue and start application"},
        )
        assert response.status_code == 302

        test_organisation = organisation.matching_test_organisation
        test_grant_recipient = get_grant_recipient_or_none(application.grant_id, test_organisation.id)
        assert test_grant_recipient is not None
        assert test_grant_recipient.mode == GrantRecipientModeEnum.TEST

        db_session.refresh(team_member)
        test_role = next(role for role in team_member.roles if role.organisation_id == test_organisation.id)
        assert RoleEnum.DATA_PROVIDER in test_role.permissions
        assert RoleEnum.CERTIFIER in test_role.permissions

    def test_signing_up_does_not_fail_when_the_organisation_has_no_matching_test_organisation(
        self, authenticated_no_role_client, application, factories
    ):
        factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id),
            data={"submit": "Continue and start application"},
        )
        assert response.status_code == 302

    def test_joins_you_to_an_organisation_that_is_already_applying(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        factories.grant_recipient.create(
            grant=application.grant, organisation=organisation, status=GrantRecipientStatusEnum.APPLYING
        )

        # no need to confirm anything; their organisation is already applying, so they just get access
        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=application.grant_id,
        )

        user = authenticated_no_role_client.user
        db_session.refresh(user)
        assert RoleEnum.DATA_PROVIDER in user.roles[0].permissions

    def test_sends_you_straight_through_when_you_already_have_access(
        self, authenticated_no_role_client, application, factories
    ):
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        factories.grant_recipient.create(
            grant=application.grant, organisation=organisation, status=GrantRecipientStatusEnum.APPLYING
        )
        factories.user_role.create(
            user=authenticated_no_role_client.user,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            organisation=organisation,
            grant=application.grant,
        )

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=application.grant_id,
        )

    def test_shows_continue_button_and_redirects_to_name_page_when_you_have_no_name(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        authenticated_no_role_client.user.name = None
        db_session.commit()

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.find("form").find("button", {"type": "submit"}).text.strip() == "Continue"

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id),
            data={"submit": "Continue"},
        )

        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.public_sign_up_name", collection_id=application.id)

    def test_joining_an_already_applying_organisation_asks_for_your_name_first_if_you_have_none(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        factories.grant_recipient.create(
            grant=application.grant, organisation=organisation, status=GrantRecipientStatusEnum.APPLYING
        )
        authenticated_no_role_client.user.name = None
        db_session.commit()

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.public_sign_up_name", collection_id=application.id)


@pytest.mark.authenticate_as(APPLICANT_EMAIL)
class TestPublicSignUpName:
    def test_asks_for_your_name_and_then_completes_sign_up(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        authenticated_no_role_client.user.name = None
        db_session.commit()

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id)
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "What is your full name?"

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Chief Cheesemonger"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=application.grant_id,
        )

        user = authenticated_no_role_client.user
        db_session.refresh(user)
        assert user.name == "Chief Cheesemonger"

        grant_recipient = get_grant_recipient_or_none(application.grant_id, organisation.id)
        assert grant_recipient is not None
        assert RoleEnum.DATA_PROVIDER in user.roles[0].permissions

    def test_completing_sign_up_also_sets_up_a_test_grant_recipient(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        organisation = factories.organisation.create(
            name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN], with_matching_test_org=True
        )
        authenticated_no_role_client.user.name = None
        db_session.commit()

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Chief Cheesemonger"},
        )
        assert response.status_code == 302

        test_grant_recipient = get_grant_recipient_or_none(
            application.grant_id, organisation.matching_test_organisation.id
        )
        assert test_grant_recipient is not None
        assert test_grant_recipient.mode == GrantRecipientModeEnum.TEST

    def test_rejects_a_blank_name(self, authenticated_no_role_client, application, factories, db_session):
        factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        authenticated_no_role_client.user.name = None
        db_session.commit()

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": ""},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter your full name")


@pytest.mark.authenticate_as(APPLICANT_EMAIL)
class TestPublicSignUpEligibilityQuestion:
    def test_eligible_redirects_to_the_first_eligibility_question_when_not_yet_submitted(
        self, authenticated_no_role_client, application_with_eligibility_check
    ):
        application, question = application_with_eligibility_check

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            collection_id=application.id,
            question_id=question.id,
        )

    def test_a_disqualifying_answer_redirects_to_the_ineligible_page(
        self, authenticated_no_role_client, application_with_eligibility_check
    ):
        application, question = application_with_eligibility_check

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                collection_id=application.id,
                question_id=question.id,
            ),
            data={question.safe_qid: "0", "submit": "Continue"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_ineligible", collection_id=application.id
        )

        response = authenticated_no_role_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "You are not eligible to apply"

    def test_a_passing_answer_completes_the_check_and_reaches_the_eligible_page(
        self, authenticated_no_role_client, application_with_eligibility_check, factories
    ):
        application, question = application_with_eligibility_check
        factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                collection_id=application.id,
                question_id=question.id,
            ),
            data={question.safe_qid: "1", "submit": "Continue"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligible", collection_id=application.id
        )

        response = authenticated_no_role_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "You are eligible to apply"

    def test_redirects_back_to_eligible_page_if_you_already_have_a_name(
        self, authenticated_no_role_client, application, factories
    ):
        factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligible", collection_id=application.id
        )


@pytest.mark.authenticate_as(APPLICANT_EMAIL)
class TestPublicSignUpClaimsSubmission:
    def test_answering_eligibility_questions_creates_an_unclaimed_submission(
        self, authenticated_no_role_client, application_with_eligibility_check
    ):
        application, question = application_with_eligibility_check

        _answer_eligibility_question(authenticated_no_role_client, application, question)

        submission = get_unclaimed_submission_for_user(
            authenticated_no_role_client.user, application, SubmissionModeEnum.LIVE
        )
        assert submission is not None
        assert submission.grant_recipient_id is None

    def test_becoming_a_grant_recipient_claims_the_unclaimed_submission(
        self, authenticated_no_role_client, application_with_eligibility_check, factories, db_session
    ):
        application, question = application_with_eligibility_check
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])

        _answer_eligibility_question(authenticated_no_role_client, application, question)
        unclaimed = get_unclaimed_submission_for_user(
            authenticated_no_role_client.user, application, SubmissionModeEnum.LIVE
        )
        assert unclaimed is not None

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id),
            data={"submit": "Continue and start application"},
        )
        assert response.status_code == 302

        grant_recipient = get_grant_recipient_or_none(application.grant_id, organisation.id)
        assert grant_recipient is not None

        db_session.refresh(unclaimed)
        assert unclaimed.grant_recipient_id == grant_recipient.id
        assert (
            get_unclaimed_submission_for_user(authenticated_no_role_client.user, application, SubmissionModeEnum.LIVE)
            is None
        )

    def test_joining_an_organisation_that_already_has_a_submission_discards_your_unclaimed_one(
        self, authenticated_no_role_client, application_with_eligibility_check, factories, db_session
    ):
        application, question = application_with_eligibility_check
        organisation = factories.organisation.create(name="Barnsley Council", trusted_domains=[TRUSTED_DOMAIN])
        grant_recipient = factories.grant_recipient.create(
            grant=application.grant, organisation=organisation, status=GrantRecipientStatusEnum.APPLYING
        )
        existing_submission = factories.submission.create(
            collection=application, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        _answer_eligibility_question(authenticated_no_role_client, application, question)
        unclaimed = get_unclaimed_submission_for_user(
            authenticated_no_role_client.user, application, SubmissionModeEnum.LIVE
        )
        assert unclaimed is not None
        unclaimed_id = unclaimed.id

        # this user has no access to the organisation yet, so they join it - the "already applying" path
        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=application.grant_id,
        )

        assert db_session.get(Submission, unclaimed_id) is None
        remaining = get_submissions_by_grant_recipient_collection(grant_recipient, application.id)
        assert [s.id for s in remaining] == [existing_submission.id]


@pytest.mark.authenticate_as(UNTRUSTED_EMAIL)
class TestPublicSignUpOrganisationRegistration:
    def test_local_authority_is_sent_to_contact_support(self, authenticated_no_role_client, application):
        client = authenticated_no_role_client

        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "local authority"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_contact_support", collection_id=application.id
        )

    def test_no_reference_number_is_sent_to_contact_support(self, authenticated_no_role_client, application):
        client = authenticated_no_role_client

        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "company"},
        )
        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "no"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_contact_support", collection_id=application.id
        )

    def test_unrecognised_reference_number_shows_a_field_error(self, authenticated_no_role_client, application):
        client = authenticated_no_role_client

        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "company"},
        )
        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "yes", "reference_number": "00000000"},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "We could not find that Companies House reference number. Check it and try again.")

    def test_not_your_organisation_is_sent_to_contact_support(self, authenticated_no_role_client, application):
        client = authenticated_no_role_client

        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "company"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "yes", "reference_number": "01234567"},
        )
        response = client.post(
            url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=application.id),
            data={"is_correct_organisation": "no"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_contact_support", collection_id=application.id
        )

    def test_company_happy_path_registers_the_organisation_and_starts_applying(
        self, authenticated_no_role_client, application, db_session
    ):
        client = authenticated_no_role_client
        client.user.name = None
        db_session.commit()

        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "company"},
        )
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id
        )

        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "yes", "reference_number": "01234567"},
        )
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_confirm_organisation", collection_id=application.id
        )

        response = client.post(
            url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=application.id),
            data={"is_correct_organisation": "yes"},
        )
        assert response.location == url_for("access_grant_funding.public_sign_up_name", collection_id=application.id)

        response = client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Ada Lovelace"},
        )
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_check_your_answers", collection_id=application.id
        )

        response = client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Northern Regeneration Partners Limited" in soup.text
        assert "01234567" in soup.text
        assert "Ada Lovelace" in soup.text

        response = client.post(response.request.path, data={"submit": "Confirm and start application"})

        organisation = (
            db_session.query(Organisation).filter_by(external_id="CH-01234567", mode=OrganisationModeEnum.LIVE).one()
        )
        assert organisation.name == "Northern Regeneration Partners Limited"
        assert organisation.type == OrganisationType.COMPANY
        assert organisation.companies_house_number == "01234567"

        test_organisation = (
            db_session.query(Organisation).filter_by(external_id="CH-01234567", mode=OrganisationModeEnum.TEST).one()
        )
        assert test_organisation.name == "Northern Regeneration Partners Limited (test)"

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections", organisation_id=organisation.id, grant_id=application.grant_id
        )

        live_grant_recipient = get_grant_recipient_or_none(application.grant_id, organisation.id)
        assert live_grant_recipient is not None
        assert live_grant_recipient.status == GrantRecipientStatusEnum.APPLYING

        test_grant_recipient = get_grant_recipient_or_none(application.grant_id, test_organisation.id)
        assert test_grant_recipient is not None
        assert test_grant_recipient.mode == GrantRecipientModeEnum.TEST

        user = client.user
        db_session.refresh(user)
        assert user.name == "Ada Lovelace"
        assert RoleEnum.DATA_PROVIDER in user.roles[0].permissions

    def test_charity_happy_path_registers_the_organisation(self, authenticated_no_role_client, application, db_session):
        client = authenticated_no_role_client
        client.user.name = None
        db_session.commit()

        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "charity"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "yes", "reference_number": "1122334"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=application.id),
            data={"is_correct_organisation": "yes"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Ada Lovelace"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_check_your_answers", collection_id=application.id),
            data={"submit": "Confirm and start application"},
        )

        organisation = (
            db_session.query(Organisation).filter_by(external_id="CC-1122334", mode=OrganisationModeEnum.LIVE).one()
        )
        assert organisation.name == "The Riverside Youth Trust"
        assert organisation.type == OrganisationType.CHARITY
        assert organisation.charity_commission_number == "1122334"

        assert get_grant_recipient_or_none(application.grant_id, organisation.id) is not None

    def test_other_happy_path_registers_the_organisation(self, authenticated_no_role_client, application, db_session):
        client = authenticated_no_role_client
        client.user.name = None
        db_session.commit()

        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "other"},
        )
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_organisation_name", collection_id=application.id
        )

        response = client.post(
            url_for("access_grant_funding.public_sign_up_organisation_name", collection_id=application.id),
            data={"organisation_name": "Our Village Hall"},
        )
        assert response.location == url_for("access_grant_funding.public_sign_up_name", collection_id=application.id)

        client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Ada Lovelace"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_check_your_answers", collection_id=application.id),
            data={"submit": "Confirm and start application"},
        )

        organisation = db_session.query(Organisation).filter_by(name="Our Village Hall").one()
        assert organisation.type == OrganisationType.OTHER
        assert organisation.external_id.startswith("FS-")

        assert get_grant_recipient_or_none(application.grant_id, organisation.id) is not None

    def test_reuses_an_existing_organisation_with_the_same_reference(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        existing = factories.organisation.create(
            name="Northern Regeneration Partners Limited",
            type=OrganisationType.COMPANY,
            external_id="CH-01234567",
        )

        client = authenticated_no_role_client
        client.user.name = None
        db_session.commit()

        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "company"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "yes", "reference_number": "01234567"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=application.id),
            data={"is_correct_organisation": "yes"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Ada Lovelace"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_check_your_answers", collection_id=application.id),
            data={"submit": "Confirm and start application"},
        )

        assert db_session.query(Organisation).filter_by(external_id="CH-01234567").count() == 1
        organisation = db_session.query(Organisation).filter_by(external_id="CH-01234567").one()
        assert organisation.id == existing.id

    def test_an_organisation_already_applying_is_sent_to_contact_support(
        self, authenticated_no_role_client, application, factories, db_session
    ):
        existing = factories.organisation.create(
            name="Northern Regeneration Partners Limited",
            type=OrganisationType.COMPANY,
            external_id="CH-01234567",
        )
        factories.grant_recipient.create(
            grant=application.grant, organisation=existing, status=GrantRecipientStatusEnum.APPLYING
        )

        client = authenticated_no_role_client
        client.user.name = None
        db_session.commit()

        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id),
            data={"organisation_type": "company"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=application.id),
            data={"has_reference_number": "yes", "reference_number": "01234567"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=application.id),
            data={"is_correct_organisation": "yes"},
        )
        client.post(
            url_for("access_grant_funding.public_sign_up_name", collection_id=application.id),
            data={"full_name": "Ada Lovelace"},
        )
        response = client.post(
            url_for("access_grant_funding.public_sign_up_check_your_answers", collection_id=application.id),
            data={"submit": "Confirm and start application"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_contact_support", collection_id=application.id
        )

        grant_recipients = db_session.query(GrantRecipient).filter_by(
            grant_id=application.grant_id, organisation_id=existing.id
        )
        assert grant_recipients.count() == 1

        user = authenticated_no_role_client.user
        db_session.refresh(user)
        assert user.roles == []

    def test_organisation_type_goes_back_to_the_email_page_when_there_is_no_eligibility_check(
        self, authenticated_no_role_client, application
    ):
        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one(".govuk-back-link")["href"] == url_for(
            "access_grant_funding.public_sign_up_email", collection_id=application.id
        )

    def test_organisation_type_goes_back_to_the_eligible_page_after_an_eligibility_check(
        self, authenticated_no_role_client, application_with_eligibility_check
    ):
        application, question = application_with_eligibility_check
        _answer_eligibility_question(authenticated_no_role_client, application, question)

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=application.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one(".govuk-back-link")["href"] == url_for(
            "access_grant_funding.public_sign_up_eligible", collection_id=application.id
        )
