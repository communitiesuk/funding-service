import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.interfaces.grant_recipients import get_grant_recipient_or_none
from app.common.data.models_user import MagicLink
from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    RoleEnum,
)
from tests.utils import get_h1_text, page_has_error

TRUSTED_DOMAIN = "barnsley.gov.uk"
APPLICANT_EMAIL = f"chief.cheesemonger@{TRUSTED_DOMAIN}"


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
        assert get_h1_text(soup) == "Cheeseboards in parks"
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
    def test_sends_you_back_to_the_email_page_when_your_domain_is_not_registered(
        self, authenticated_no_role_client, application, factories
    ):
        factories.organisation.create(name="Barnsley Council", trusted_domains=["somewhere-else.gov.uk"])

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.public_sign_up_eligible", collection_id=application.id)
        )

        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.public_sign_up_email", collection_id=application.id)

        # ... and the email page tells them to talk to the service desk, with their address prefilled
        response = authenticated_no_role_client.get(response.location)
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "We could not match your email address to an organisation")
        assert soup.find("input", {"name": "email_address"})["value"] == APPLICANT_EMAIL

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
