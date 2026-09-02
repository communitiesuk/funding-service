import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask_login import login_user
from sqlalchemy import select

from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType
from app.common.data.models import GrantRecipient, Organisation
from app.common.data.models_user import UserRole
from app.common.data.types import (
    AuthMethodEnum,
    CollectionStatusEnum,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    OrganisationStatus,
    OrganisationType,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.helpers.collections import get_or_create_unclaimed_submission
from tests.utils import get_h1_text, get_summary_list_value_by_key


@pytest.fixture()
def sign_up_collection(factories):
    grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
    return factories.collection.create(
        grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
    )


def _seed_session(client, collection, org_session: CreateOrganisationSession | None = None) -> None:
    with client.session_transaction() as flask_session:
        flask_session["signing_up_for_collection_id"] = collection.id
        if org_session is not None:
            flask_session["create_organisation"] = org_session.to_session_dict()


def _eligible_to_apply_url(collection):
    return url_for(
        "access_grant_funding.eligible_to_apply",
        grant_slug=collection.grant.slug,
        collection_slug=collection.slug,
    )


class TestCreateOrganisationType:
    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(collection_id=sign_up_collection.id),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What is your organisation type?" in get_h1_text(soup)
        assert "Create organisation" in soup.text

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_session_for_another_collection_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(collection_id=uuid.uuid4()),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_saves_choice_and_continues_to_name(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(collection_id=sign_up_collection.id),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.CHARITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["organisation_type"] == SignUpOrganisationType.CHARITY.value

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_local_authority_goes_to_the_support_desk_page(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(collection_id=sign_up_collection.id),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.LOCAL_AUTHORITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_local_authority",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        # the choice is still stored so the support desk page can tell it is the right place to be
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert (
                flask_session["create_organisation"]["organisation_type"]
                == SignUpOrganisationType.LOCAL_AUTHORITY.value
            )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_local_authority_from_check_your_answers_keeps_the_source(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"organisation_type": SignUpOrganisationType.LOCAL_AUTHORITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_local_authority",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_post_from_check_your_answers_returns_there(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        cya_url = url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )
        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        back_link = soup.select_one("a.govuk-back-link")
        assert back_link["href"] == cya_url

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"organisation_type": SignUpOrganisationType.COMPANY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == cya_url


class TestCreateOrganisationLocalAuthority:
    def _url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_local_authority",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    def _organisation_type_url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_page(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.LOCAL_AUTHORITY
            ),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Contact our support desk" in get_h1_text(soup)
        assert "Create organisation" in soup.text
        assert soup.select_one("a.govuk-back-link")["href"] == self._organisation_type_url(sign_up_collection)

        support_desk_link = soup.find("a", string="support desk (opens in new tab)")
        assert support_desk_link is not None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_another_organisation_type_redirects_back_to_the_type_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.CHARITY
            ),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == self._organisation_type_url(sign_up_collection)


class TestCreateOrganisationName:
    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What is the name of your organisation?" in get_h1_text(soup)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_persists_name_and_generates_external_id(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "  Acme Ltd  ", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            stored = flask_session["create_organisation"]
        assert stored["name"] == "Acme Ltd"
        assert len(stored["external_id"]) == 9

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_an_existing_organisation_name_goes_to_the_already_exists_page(
        self, authenticated_no_role_client, sign_up_collection, factories
    ):
        factories.organisation.create(name="Acme Ltd")
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "acme ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        # the name is still stored so the page can name the organisation and the back link pre-fills what they typed
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["name"] == "acme ltd"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_an_existing_organisation_name_from_check_your_answers_keeps_the_source(
        self, authenticated_no_role_client, sign_up_collection, factories
    ):
        factories.organisation.create(name="Acme Ltd")
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Some other name",
                external_id="000111222",
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"name": "Acme Ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_a_name_only_taken_in_test_mode_continues(
        self, authenticated_no_role_client, sign_up_collection, factories
    ):
        factories.organisation.create(name="Acme Ltd", mode=OrganisationModeEnum.TEST)
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "Acme Ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    def test_post_matches_the_test_suffixed_name_for_a_deliver_user_testing_access(
        self, anonymous_client, sign_up_collection, factories, user, db_session
    ):
        # ` (test)` should reliably be matched
        factories.organisation.create(name="Mirrored Org (test)", mode=OrganisationModeEnum.TEST)
        factories.user_role.create(
            user=user,
            organisation=sign_up_collection.grant.organisation,
            grant=sign_up_collection.grant,
            permissions=[RoleEnum.MEMBER],
        )

        # logging in as a deliver user means the session will all be in the test context
        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        _seed_session(
            anonymous_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = anonymous_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "Mirrored Org", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_post_from_check_your_answers_returns_there(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Acme Ltd",
                external_id="000111222",
            ),
        )

        cya_url = url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        get_response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            )
        )
        soup = BeautifulSoup(get_response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == cya_url

        post_response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"name": "Acme Ltd", "submit": "y"},
        )
        assert post_response.status_code == 302
        assert post_response.location == cya_url


class TestCreateOrganisationAlreadyExists:
    @pytest.fixture()
    def duplicate_org_session(self, sign_up_collection, factories):
        factories.organisation.create(name="Acme Ltd")
        return CreateOrganisationSession(
            collection_id=sign_up_collection.id,
            organisation_type=SignUpOrganisationType.OTHER,
            name="Acme Ltd",
            external_id="000111222",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_page(self, authenticated_no_role_client, sign_up_collection, duplicate_org_session):
        _seed_session(authenticated_no_role_client, sign_up_collection, duplicate_org_session)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Your organisation already exists" in get_h1_text(soup)
        assert "Acme Ltd is already an existing organisation on Access grant funding." in soup.text

        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_from_check_your_answers_back_link_keeps_the_source(
        self, authenticated_no_role_client, sign_up_collection, duplicate_org_session
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, duplicate_org_session)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_a_name_in_the_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_a_name_that_is_not_taken_redirects_back_to_the_name_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Nobody Else Ltd",
                external_id="000111222",
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )


class TestCreateOrganisationUserName:
    def _org_session(self, collection, **kwargs) -> CreateOrganisationSession:
        return CreateOrganisationSession(
            collection_id=collection.id,
            organisation_type=SignUpOrganisationType.OTHER,
            name="Acme Ltd",
            external_id="000111222",
            **kwargs,
        )

    def _url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    def _cya_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection, db_session):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection, self._org_session(sign_up_collection))

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What is your full name?" in get_h1_text(soup)
        assert "Create organisation" in soup.text

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_prefills_a_name_already_in_the_session(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one("input[name='user_name']")["value"] == "Test applicant"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection, db_session):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_skips_the_step_when_we_already_hold_a_name(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._org_session(sign_up_collection))

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert authenticated_no_role_client.user.name
        assert response.status_code == 302
        assert response.location == self._cya_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_persists_the_name_to_the_session_and_continues(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection, self._org_session(sign_up_collection))

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection), data={"user_name": "  Test applicant  ", "submit": "y"}
        )

        assert response.status_code == 302
        assert response.location == self._cya_url(sign_up_collection)

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["user_name"] == "Test applicant"

        # the name only reaches the user record when they confirm their answers
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name is None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_source_round_trip_back_to_check_your_answers(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, user_name="Test applicant"),
        )

        get_response = authenticated_no_role_client.get(self._url(sign_up_collection, source="check-your-answers"))
        soup = BeautifulSoup(get_response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == self._cya_url(sign_up_collection)

        post_response = authenticated_no_role_client.post(
            self._url(sign_up_collection, source="check-your-answers"),
            data={"user_name": "Grace Hopper", "submit": "y"},
        )
        assert post_response.status_code == 302
        assert post_response.location == self._cya_url(sign_up_collection)


class TestCreateOrganisationCheckYourAnswers:
    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_answers_with_change_links(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id,
                organisation_type=SignUpOrganisationType.CHARITY,
                name="Acme Ltd",
                external_id="000111222",
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Confirm your details are correct" in get_h1_text(soup)
        assert get_summary_list_value_by_key(soup, "Email address").text.strip() == "applicant@no-org.com"
        assert get_summary_list_value_by_key(soup, "Organisation type").text.strip() == "Charity"
        assert get_summary_list_value_by_key(soup, "Organisation name").text.strip() == "Acme Ltd"

        change_type = url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        change_name = url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        hrefs = {a["href"] for a in soup.select("a")}
        assert change_type in hrefs
        assert change_name in hrefs

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_shows_a_name_we_already_hold_without_a_change_link(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_summary_list_value_by_key(soup, "Full name").text.strip() == authenticated_no_role_client.user.name

        change_user_name = url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        assert change_user_name not in {a["href"] for a in soup.select("a")}
        # the step was never shown, so back goes to the one before it
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_shows_the_name_from_the_session_with_a_change_link(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_summary_list_value_by_key(soup, "Full name").text.strip() == "Test applicant"

        change_user_name = url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        assert change_user_name in {a["href"] for a in soup.select("a")}
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_a_complete_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)

    def _complete_session(self, collection, **kwargs) -> CreateOrganisationSession:
        return CreateOrganisationSession(
            collection_id=collection.id,
            organisation_type=SignUpOrganisationType.OTHER,
            name="Acme Ltd",
            external_id="000111222",
            **kwargs,
        )

    def _cya_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_creates_the_organisation_grant_recipient_and_data_provider_role(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        assert organisation.name == "Acme Ltd"
        assert organisation.type == OrganisationType.OTHER
        assert organisation.custom_code == "000111222"
        assert organisation.mode == OrganisationModeEnum.LIVE
        assert organisation.status == OrganisationStatus.ACTIVE
        assert organisation.can_manage_grants is False
        assert organisation.domains == []

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == sign_up_collection.grant.id,
                GrantRecipient.organisation_id == organisation.id,
            )
        ).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == GrantRecipientModeEnum.LIVE

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_no_role_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == sign_up_collection.grant.id,
            )
        ).one()
        assert RoleEnum.DATA_PROVIDER in user_role.permissions
        assert RoleEnum.MEMBER in user_role.permissions

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=sign_up_collection.grant.id,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "create_organisation" not in flask_session
            assert "signing_up_for_collection_id" not in flask_session

        followed_response = authenticated_no_role_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        assert (
            "You've been added to Acme Ltd. You can now apply for Test grant name."
            in BeautifulSoup(followed_response.data, "html.parser").text
        )

    def test_post_creates_a_test_organisation_for_a_deliver_user_testing_access(
        self, anonymous_client, sign_up_collection, factories, user, db_session
    ):
        factories.user_role.create(
            user=user,
            organisation=sign_up_collection.grant.organisation,
            grant=sign_up_collection.grant,
            permissions=[RoleEnum.MEMBER],
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        _seed_session(anonymous_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = anonymous_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        assert organisation.name == "Acme Ltd (test)"
        assert organisation.mode == OrganisationModeEnum.TEST

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(GrantRecipient.organisation_id == organisation.id)
        ).one()
        assert grant_recipient.mode == GrantRecipientModeEnum.TEST

        assert response.status_code == 302

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_claims_the_eligibility_submission(self, authenticated_no_role_client, sign_up_collection, db_session):
        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_no_role_client.user, sign_up_collection, SubmissionModeEnum.LIVE
        ).submission
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})
        assert response.status_code == 302

        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(GrantRecipient.organisation_id == organisation.id)
        ).one()

        db_session.refresh(unclaimed_submission)
        assert unclaimed_submission.grant_recipient_id == grant_recipient.id

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_sets_the_users_name_from_the_session(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name == "Test applicant"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_leaves_a_name_we_already_hold_alone(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        existing_name = authenticated_no_role_client.user.name
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name == existing_name

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_does_not_set_the_users_name_when_the_organisation_name_was_taken(
        self, authenticated_no_role_client, sign_up_collection, factories, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, user_name="Test applicant"),
        )
        factories.organisation.create(name="Acme Ltd", mode=OrganisationModeEnum.LIVE)

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name is None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_redirects_to_already_exists_when_the_name_was_taken_in_the_meantime(
        self, authenticated_no_role_client, sign_up_collection, factories, db_session
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))
        factories.organisation.create(name="Acme Ltd", mode=OrganisationModeEnum.LIVE)

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

        assert db_session.scalars(select(GrantRecipient)).all() == []

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_twice_creates_a_single_organisation_and_grant_recipient(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        for _ in range(2):
            _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))
            authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert (
            db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one() is not None
        )
        assert len(db_session.scalars(select(GrantRecipient)).all()) == 1

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_without_a_complete_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            CreateOrganisationSession(
                collection_id=sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER
            ),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        assert response.location == _eligible_to_apply_url(sign_up_collection)
