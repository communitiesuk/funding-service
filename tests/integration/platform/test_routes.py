from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import select

from app.common.data.models import Grant
from app.platform import GrantForm


def test_list_grants(client, factories, templates_rendered):
    factories.grant.create_batch(5)
    result = client.get("/grants")
    assert result.status_code == 200
    assert len(templates_rendered[0][1]["grants"]) == 5
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text == "My grants"


def test_view_grant_dashboard(client, factories, templates_rendered):
    grant = factories.grant.create()
    result = client.get(url_for("platform.view_grant", grant_id=grant.id))
    assert result.status_code == 200
    assert templates_rendered[0][1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text == grant.name


def test_view_grant_settings(client, factories, templates_rendered):
    grant = factories.grant.create()
    result = client.get(url_for("platform.grant_settings", grant_id=grant.id))
    assert result.status_code == 200
    assert templates_rendered[0][1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert grant.name in soup.h1.text.strip()
    assert "Settings" in soup.h1.text.strip()


def test_grant_change_name_get(client, factories, templates_rendered):
    grant = factories.grant.create()
    result = client.get(url_for("platform.grant_change_name", grant_id=grant.id))
    assert result.status_code == 200
    template = next(
        template for template in templates_rendered if template[0].name == "platform/settings/grant_change_name.html"
    )
    assert template[1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert "Change grant name" in soup.h1.text.strip()


def test_grant_change_name_post(client, factories, templates_rendered, db_session):
    grant = factories.grant.create()
    # Update the name
    form = GrantForm()
    form.name.data = "New name"
    result = client.post(
        url_for("platform.grant_change_name", grant_id=grant.id), data=form.data, follow_redirects=False
    )
    assert result.status_code == 302

    # Check the update is in the database
    grant_from_db = db_session.get(Grant, grant.id)
    assert grant_from_db.name == "New name"


def test_grant_change_name_post_with_errors(client, factories, templates_rendered):
    grants = factories.grant.create_batch(2)
    # Test error handling on an update
    form = GrantForm(data={"name": grants[1].name})
    result = client.post(
        url_for("platform.grant_change_name", grant_id=grants[0].id), data=form.data, follow_redirects=False
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#name")) == 1
    assert soup.find_all("a", href="#name")[0].text.strip() == "Grant name already in use"


def test_create_grant(client, db_session):
    url = url_for("platform.create_grant")
    client.get(url)
    response = client.post(
        url,
        data={"name": "My test grant"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    db_session.scalars(select(Grant).where(Grant.name == "My test grant")).one()
    assert response.status_code == 302
