from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Grant
from app.deliver_grant_funding.forms import GrantContactForm, GrantDescriptionForm, GrantGGISForm, GrantNameForm
from tests.utils import get_h1_text, get_h2_text


class TestViewGrantDetails:
    def test_as_platform_admin(self, authenticated_platform_admin_client, factories, templates_rendered):
        grant = factories.grant.create()
        result = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=grant.id)
        )
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_details").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert grant.name in get_h1_text(soup)
        assert "Grant details" in get_h1_text(soup)

        change_links = [link for link in soup.select("a") if "Change" in link.get_text()]
        assert {link.get_text().strip() for link in change_links} == {
            "Change GGIS reference number",
            "Change grant name",
            "Change main contact",
            "Change main purpose",
        }

    def test_as_grant_admin(self, authenticated_grant_admin_client, factories, templates_rendered):
        grant = authenticated_grant_admin_client.grant
        result = authenticated_grant_admin_client.get(url_for("deliver_grant_funding.grant_details", grant_id=grant.id))
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_details").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert grant.name in get_h1_text(soup)
        assert "Grant details" in get_h1_text(soup)

        change_links = [link for link in soup.select("a") if "Change" in link.get_text()]
        assert {link.get_text().strip() for link in change_links} == {
            "Change grant name",
            "Change main contact",
            "Change main purpose",
        }

    def test_as_grant_member(self, authenticated_grant_member_client, factories, templates_rendered):
        grant = authenticated_grant_member_client.grant
        result = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=grant.id)
        )
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_details").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert grant.name in get_h1_text(soup)
        assert "Grant details" in get_h1_text(soup)

        change_links = [link for link in soup.select("a") if "Change" in link.get_text()]
        assert {link.get_text().strip() for link in change_links} == set()


class TestChangeGGIS:
    def test_grant_change_ggis_get(self, authenticated_platform_admin_client, factories, templates_rendered):
        grant = factories.grant.create()
        result = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.grant_change_ggis", grant_id=grant.id)
        )
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_change_ggis").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert "What is the GGIS reference number?" in get_h1_text(soup)

    def test_grant_change_ggis_post(
        self, authenticated_platform_admin_client, factories, templates_rendered, db_session
    ):
        grant = factories.grant.create()
        # Update the name
        form = GrantGGISForm()
        form.has_ggis.data = "yes"
        form.ggis_number.data = "New number"
        result = authenticated_platform_admin_client.post(
            url_for("deliver_grant_funding.grant_change_ggis", grant_id=grant.id),
            data=form.data,
            follow_redirects=False,
        )
        assert result.status_code == 302
        assert result.location == url_for(
            "deliver_grant_funding.grant_details",
            grant_id=grant.id,
        )

        # Check the update is in the database
        grant_from_db = db_session.get(Grant, grant.id)
        assert grant_from_db.ggis_number == "New number"


class TestChangeGrantName:
    def test_grant_change_name_get(self, authenticated_grant_admin_client, factories, templates_rendered):
        grant = authenticated_grant_admin_client.grant
        result = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.grant_change_name", grant_id=grant.id)
        )
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_change_name").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert "What is the name of this grant?" in get_h1_text(soup)

    def test_grant_change_name_post(
        self, authenticated_platform_admin_client, factories, templates_rendered, db_session
    ):
        grant = factories.grant.create()
        # Update the name
        form = GrantNameForm()
        form.name.data = "New name"
        result = authenticated_platform_admin_client.post(
            url_for("deliver_grant_funding.grant_change_name", grant_id=grant.id),
            data=form.data,
            follow_redirects=False,
        )
        assert result.status_code == 302
        assert result.location == url_for(
            "deliver_grant_funding.grant_details",
            grant_id=grant.id,
        )

        # Check the update is in the database
        grant_from_db = db_session.get(Grant, grant.id)
        assert grant_from_db.name == "New name"

    def test_grant_change_name_post_with_errors(
        self, authenticated_platform_admin_client, factories, templates_rendered
    ):
        grants = factories.grant.create_batch(2)
        # Test error handling on an update
        form = GrantNameForm(data={"name": grants[1].name})
        result = authenticated_platform_admin_client.post(
            url_for("deliver_grant_funding.grant_change_name", grant_id=grants[0].id),
            data=form.data,
            follow_redirects=False,
        )
        assert result.status_code == 200

        soup = BeautifulSoup(result.data, "html.parser")
        assert get_h2_text(soup) == "There is a problem"
        assert len(soup.find_all("a", href="#name")) == 1
        assert soup.find_all("a", href="#name")[0].text.strip() == "Grant name already in use"


class TestChangeGrantDescription:
    def test_grant_change_description_get(self, authenticated_grant_admin_client, factories, templates_rendered):
        grant = authenticated_grant_admin_client.grant
        result = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.grant_change_description", grant_id=grant.id)
        )
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_change_description").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert "What is the main purpose of this grant?" in get_h1_text(soup)

    def test_grant_change_description_post(
        self, authenticated_platform_admin_client, factories, templates_rendered, db_session
    ):
        grant = factories.grant.create()
        # Update the name
        form = GrantDescriptionForm()
        form.description.data = "New description"
        result = authenticated_platform_admin_client.post(
            url_for("deliver_grant_funding.grant_change_description", grant_id=grant.id),
            data=form.data,
            follow_redirects=False,
        )
        assert result.status_code == 302
        assert result.location == url_for(
            "deliver_grant_funding.grant_details",
            grant_id=grant.id,
        )

        # Check the update is in the database
        grant_from_db = db_session.get(Grant, grant.id)
        assert grant_from_db.description == "New description"


class TestChangeGrantContact:
    def test_grant_change_contact_get(self, authenticated_grant_admin_client, factories, templates_rendered):
        grant = authenticated_grant_admin_client.grant
        result = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.grant_change_contact", grant_id=grant.id)
        )
        assert result.status_code == 200
        assert templates_rendered.get("deliver_grant_funding.grant_change_contact").context.get("grant") == grant
        soup = BeautifulSoup(result.data, "html.parser")
        assert "Who is the main contact for this grant?" in get_h1_text(soup)

    def test_grant_change_contact_post(
        self, authenticated_platform_admin_client, factories, templates_rendered, db_session
    ):
        grant = factories.grant.create()
        # Update the name
        form = GrantContactForm()
        form.primary_contact_name.data = "New name"
        form.primary_contact_email.data = "new@email.com"
        result = authenticated_platform_admin_client.post(
            url_for("deliver_grant_funding.grant_change_contact", grant_id=grant.id),
            data=form.data,
            follow_redirects=False,
        )
        assert result.status_code == 302
        assert result.location == url_for(
            "deliver_grant_funding.grant_details",
            grant_id=grant.id,
        )

        # Check the update is in the database
        grant_from_db = db_session.get(Grant, grant.id)
        assert grant_from_db.primary_contact_name == "New name"
        assert grant_from_db.primary_contact_email == "new@email.com"
