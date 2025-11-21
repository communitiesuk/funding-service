from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Grant
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.forms import GrantContactForm, GrantDescriptionForm, GrantGGISForm, GrantNameForm
from tests.utils import get_form_data, get_h1_text, get_h2_text


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

    def test_displays_recipients_with_data_providers_and_certifiers(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()

        org_a = factories.organisation.create(name="Organisation A")
        org_b = factories.organisation.create(name="Organisation B")
        org_c = factories.organisation.create(name="Organisation C")

        factories.grant_recipient.create(grant=grant, organisation=org_a)
        factories.grant_recipient.create(grant=grant, organisation=org_b)
        factories.grant_recipient.create(grant=grant, organisation=org_c)

        certifier_1_a = factories.user.create(name="Charlie Brown", email="charlie@org-a.com")
        data_provider_1_a = factories.user.create(name="Alice Smith", email="alice@org-a.com")
        data_provider_2_a = factories.user.create(name="Bob Jones", email="bob@org-a.com")

        data_provider_1_b = factories.user.create(name="David Wilson", email="david@org-b.com")
        certifier_1_b = factories.user.create(name="Eve Davis", email="eve@org-b.com")
        certifier_2_b = factories.user.create(name="Frank Miller", email="frank@org-b.com")

        data_provider_1_c = factories.user.create(name="Grace Taylor", email="grace@org-c.com")
        certifier_1_c = factories.user.create(name="Henry Anderson", email="henry@org-c.com")

        factories.user_role.create(
            user=data_provider_1_a,
            organisation=org_a,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=data_provider_2_a,
            organisation=org_a,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=certifier_1_a,
            organisation=org_a,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        factories.user_role.create(
            user=data_provider_1_b,
            organisation=org_b,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=certifier_1_b,
            organisation=org_b,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        factories.user_role.create(
            user=certifier_2_b,
            organisation=org_b,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        factories.user_role.create(
            user=data_provider_1_c,
            organisation=org_c,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=certifier_1_c,
            organisation=org_c,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        result = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=grant.id)
        )
        assert result.status_code == 200

        soup = BeautifulSoup(result.data, "html.parser")

        recipients_heading = soup.find("h2", string="Recipients")
        assert recipients_heading is not None

        table = soup.find("table", class_="govuk-table")
        assert table is not None

        headers = table.find_all("th")
        assert len(headers) == 2
        assert headers[0].get_text().strip() == "Grant recipient"
        assert headers[1].get_text().strip() == "Users"

        rows = table.find("tbody").find_all("tr")
        assert len(rows) == 3

        assert "Organisation A" in rows[0].get_text()
        assert "Alice Smith (alice@org-a.com)" in rows[0].get_text()
        assert "Bob Jones (bob@org-a.com)" in rows[0].get_text()
        assert "Charlie Brown (charlie@org-a.com)" in rows[0].get_text()

        assert "Organisation B" in rows[1].get_text()
        assert "David Wilson (david@org-b.com)" in rows[1].get_text()
        assert "Eve Davis (eve@org-b.com)" in rows[1].get_text()
        assert "Frank Miller (frank@org-b.com)" in rows[1].get_text()

        assert "Organisation C" in rows[2].get_text()
        assert "Grace Taylor (grace@org-c.com)" in rows[2].get_text()
        assert "Henry Anderson (henry@org-c.com)" in rows[2].get_text()

        row_0_text = rows[0].get_text()
        alice_pos = row_0_text.find("Alice Smith")
        bob_pos = row_0_text.find("Bob Jones")
        assert alice_pos < bob_pos

        row_1_text = rows[1].get_text()
        eve_pos = row_1_text.find("Eve Davis")
        frank_pos = row_1_text.find("Frank Miller")
        assert eve_pos < frank_pos

    def test_displays_no_recipients_message(self, authenticated_platform_admin_client, factories):
        grant = factories.grant.create()

        result = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=grant.id)
        )
        assert result.status_code == 200

        soup = BeautifulSoup(result.data, "html.parser")

        recipients_heading = soup.find("h2", string="Recipients")
        assert recipients_heading is not None

        table = soup.find("table", class_="govuk-table")
        assert table is not None

        rows = table.find("tbody").find_all("tr")
        assert len(rows) == 1
        assert "No grant recipients have been set up yet" in rows[0].get_text()

    def test_displays_no_certifiers_message(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(name="Test Organisation")
        factories.grant_recipient.create(grant=grant, organisation=org)

        data_provider = factories.user.create(name="Jane Doe", email="jane@test.com")
        factories.user_role.create(
            user=data_provider,
            organisation=org,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        result = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=grant.id)
        )
        assert result.status_code == 200

        soup = BeautifulSoup(result.data, "html.parser")

        table = soup.find("table", class_="govuk-table")
        assert table is not None

        rows = table.find("tbody").find_all("tr")
        assert len(rows) == 1

        row_text = rows[0].get_text()
        assert "Test Organisation" in row_text
        assert "Jane Doe (jane@test.com)" in row_text
        assert "No certifiers have been set up" in row_text


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
            data=get_form_data(form),
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
            data=get_form_data(form),
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
            data=get_form_data(form),
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
            data=get_form_data(form),
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
            data=get_form_data(form),
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
