from uuid import UUID

from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Grant
from app.common.forms import GenericSubmitForm
from app.deliver_grant_funding.forms import GrantContactForm, GrantDescriptionForm, GrantGGISForm, GrantNameForm
from tests.utils import get_h1_text, get_h2_text


class TestGrantSetupIntro:
    def test_grant_setup_intro_get(self, authenticated_org_admin_client):
        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_intro"))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Tell us about the grant"

    def test_grant_setup_intro_post(self, authenticated_org_admin_client):
        intro_form = GenericSubmitForm()
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_intro"), data=intro_form.data, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_ggis")

    def test_grant_setup_intro_permissions(self, org_admin_access_control):
        """Test that only platform admins and org admins with can_manage_grants can access grant setup"""
        client, expected_status_code = org_admin_access_control
        response = client.get(url_for("deliver_grant_funding.grant_setup_intro"))
        assert response.status_code == expected_status_code


class TestGrantSetupGgis:
    def test_grant_setup_ggis_get_with_session(self, authenticated_org_admin_client):
        # Set up session state first
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_ggis"))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Do you have a Government Grants Information System (GGIS) reference number?"

    def test_grant_setup_ggis_get_without_session_redirects(self, authenticated_org_admin_client):
        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_ggis"))
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_intro")

    def test_grant_setup_ggis_post_with_ggis(self, authenticated_org_admin_client):
        # Set up session state first
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        ggis_form = GrantGGISForm(has_ggis="yes", ggis_number="GGIS_TEST_123")
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_ggis"), data=ggis_form.data, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_name")

    def test_grant_setup_ggis_post_no_ggis_redirects_to_required_info(self, authenticated_org_admin_client):
        # Set up session state first
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        ggis_form = GrantGGISForm(has_ggis="no")
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_ggis"), data=ggis_form.data, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_ggis_required_info")

    def test_grant_setup_ggis_required_info_get(self, authenticated_org_admin_client):
        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_ggis_required_info"))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You need to have a GGIS reference number before you can add this grant" in get_h1_text(soup)


class TestGrantSetupName:
    def test_grant_setup_name_get_with_session(self, authenticated_org_admin_client):
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_name"))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "What is the name of this grant?"

    def test_grant_setup_name_post(self, authenticated_org_admin_client):
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        name_form = GrantNameForm(name="Test Grant Name")
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_name"), data=name_form.data, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_description")


class TestGrantSetupDescription:
    def test_grant_setup_description_get_with_session(self, authenticated_org_admin_client):
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_description"))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "What is the main purpose of this grant?"

    def test_grant_setup_description_post_too_long(self, authenticated_org_admin_client):
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        long_description = " ".join(["word"] * 201)
        desc_form = GrantDescriptionForm(description=long_description)
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_description"), data=desc_form.data, follow_redirects=False
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h2_text(soup) == "There is a problem"
        assert len(soup.find_all("a", href="#description")) == 1
        assert "Description must be 200 words or fewer" in soup.find_all("a", href="#description")[0].text.strip()

    def test_grant_setup_description_post_valid(self, authenticated_org_admin_client):
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        desc_form = GrantDescriptionForm(description="A valid description under 200 words.")
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_description"), data=desc_form.data, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_contact")


class TestGrantSetupContact:
    def test_grant_setup_contact_get_with_session(self, authenticated_org_admin_client):
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        response = authenticated_org_admin_client.get(url_for("deliver_grant_funding.grant_setup_contact"))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Who is the main contact for this grant?"

    def test_grant_setup_contact_post_valid(self, authenticated_org_admin_client):
        # Set up session with required data for grant creation
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {}

        contact_form = GrantContactForm(primary_contact_name="Test Contact", primary_contact_email="test@example.com")
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_contact"), data=contact_form.data, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.grant_setup_check_your_answers")


class TestGrantSetupCheckYourAnswers:
    def test_grant_check_your_answers_post_creates_grant(self, authenticated_org_admin_client, db_session):
        # Set up session with required data for grant creation
        with authenticated_org_admin_client.session_transaction() as sess:
            sess["grant_setup"] = {
                "name": "Test Grant",
                "description": "Test description",
                "has_ggis": "yes",
                "ggis_number": "GGIS123",
                "primary_contact_name": "Joe Bloggs",
                "primary_contact_email": "joe.bloggs@gmail.com",
            }

        contact_form = GenericSubmitForm()
        response = authenticated_org_admin_client.post(
            url_for("deliver_grant_funding.grant_setup_check_your_answers"),
            data=contact_form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        # Extract grant ID from redirect URL and verify grant exists
        grant_id_str = response.location.split("/")[-2]
        grant_id = UUID(grant_id_str)
        grant_from_db = db_session.get(Grant, grant_id)
        assert grant_from_db is not None
        assert grant_from_db.primary_contact_name == "Joe Bloggs"
        assert grant_from_db.primary_contact_email == "joe.bloggs@gmail.com"
        assert grant_from_db.name == "Test Grant"
        assert grant_from_db.description == "Test description"
        assert grant_from_db.ggis_number == "GGIS123"

        # Verify redirect was to grant setup confirmation page
        assert response.location == url_for("deliver_grant_funding.grant_details", grant_id=grant_id_str)
