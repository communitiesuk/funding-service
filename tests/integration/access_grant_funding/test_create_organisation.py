import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType
from app.common.data.types import CollectionStatusEnum, GrantStatusEnum
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
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            stored = flask_session["create_organisation"]
        assert stored["name"] == "Acme Ltd"
        assert len(stored["external_id"]) == 9

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
