from bs4 import BeautifulSoup

from app.common.data.models import Grant
from app.platform import GrantForm


def test_view_all_grants(client, factories, templates_rendered):
    factories.grant.create_batch(5)
    result = client.get("/grants")
    assert result.status_code == 200
    assert len(templates_rendered[0][1]["grant_list"]) == 5
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text == "All grants"


def test_view_grant_dashboard(client, factories, templates_rendered):
    grant = factories.grant.create()
    result = client.get(f"/grants/{grant.id}")
    assert result.status_code == 200
    assert templates_rendered[0][1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text == grant.name


def test_view_grant_settings(client, factories, templates_rendered):
    grant = factories.grant.create()
    result = client.get(f"/grants/{grant.id}/settings")
    assert result.status_code == 200
    assert templates_rendered[0][1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert grant.name in soup.h1.text.strip()
    assert "Settings" in soup.h1.text.strip()


def test_edit_grant(client, factories, templates_rendered, db):
    grants = factories.grant.create_batch(2)
    grant = grants[0]
    result = client.get(f"/grants/{grant.id}/edit")
    assert result.status_code == 200
    template = next(template for template in templates_rendered if template[0].name == "platform/edit_grant.html")
    assert template[1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert grant.name in soup.h1.text.strip()
    assert "Edit grant details" in soup.h1.text.strip()

    # Update the name
    form = GrantForm()
    form.name.data = "New name"
    result = client.post(f"/grants/{grant.id}/edit", data=form.data, follow_redirects=False)
    assert result.status_code == 302

    # Check the update is in the database
    grant_from_db = db.session.get(Grant, grant.id)
    assert grant_from_db.name == "New name"

    # Test error handling on an update
    form = GrantForm()
    form.name.data = grants[1].name
    result = client.post(f"/grants/{grant.id}/edit", data=form.data, follow_redirects=False)
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#name")) == 1
    assert soup.find_all("a", href="#name")[0].text.strip() == "Grant name already in use"
