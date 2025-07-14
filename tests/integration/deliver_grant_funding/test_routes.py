from uuid import UUID

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import select

from app.common.data.interfaces.user import get_current_user
from app.common.data.models import Collection, Form, Grant, Question, Section
from app.common.data.models_user import Invitation
from app.common.data.types import ExpressionType, QuestionDataType, RoleEnum
from app.common.forms import GenericSubmitForm
from app.deliver_grant_funding.forms import (
    CollectionForm,
    FormForm,
    GrantContactForm,
    GrantDescriptionForm,
    GrantGGISForm,
    GrantNameForm,
    QuestionForm,
    QuestionTypeForm,
    SectionForm,
)
from tests.utils import get_h1_text, get_h2_text


def test_list_grants_as_admin(
    app, authenticated_platform_admin_client, factories, templates_rendered, track_sql_queries
):
    factories.grant.create_batch(5)
    with track_sql_queries() as queries:
        result = authenticated_platform_admin_client.get("/grants")
    assert result.status_code == 200
    assert len(templates_rendered.get("deliver_grant_funding.list_grants").context.get("grants")) == 5
    soup = BeautifulSoup(result.data, "html.parser")
    button = soup.find("a", string=lambda text: text and "Set up a grant" in text)
    assert button is not None, "'Set up a grant' button not found"
    headers = soup.find_all("th")
    header_texts = [th.get_text(strip=True) for th in headers]
    expected_headers = ["Grant", "GGIS number", "Email"]
    for expected in expected_headers:
        assert expected in header_texts, f"Header '{expected}' not found in table"
    assert get_h1_text(soup) == "Grants"
    assert len(queries) == 3  # 1) select user, 2) select user_role, 3) select grants


def test_list_grants_as_member_with_single_grant(
    app, authenticated_grant_member_client, factories, templates_rendered, track_sql_queries
):
    with track_sql_queries() as queries:
        result = authenticated_grant_member_client.get("/grants", follow_redirects=True)
    assert result.status_code == 200
    soup = BeautifulSoup(result.data, "html.parser")

    nav_items = [item.text.strip() for item in soup.select(".govuk-service-navigation__item")]
    assert nav_items == ["Grant details", "Grant team"]
    assert len(queries) == 3  # 1) select user, 2) select user_role, 3) select grants


def test_list_grants_as_member_with_multiple_grants(
    app, authenticated_grant_member_client, factories, templates_rendered, track_sql_queries
):
    grants = factories.grant.create_batch(5)
    user = get_current_user()
    for grant in grants:
        factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.MEMBER, grant=grant)

    result = authenticated_grant_member_client.get("/grants")
    assert result.status_code == 200
    soup = BeautifulSoup(result.data, "html.parser")
    button = soup.find("a", string=lambda text: text and "Set up a grant" in text)
    assert button is None, "'Set up a grant' button found"
    headers = soup.find_all("th")
    header_texts = [th.get_text(strip=True) for th in headers]
    expected_headers = ["Grant", "GGIS number", "Email"]
    for expected in expected_headers:
        assert expected in header_texts, f"Header '{expected}' not found in table"
    assert get_h1_text(soup) == "Grants"


@pytest.mark.authenticate_as("test@google.com")
def test_list_grant_requires_mhclg_user(authenticated_no_role_client, factories, templates_rendered):
    response = authenticated_no_role_client.get("/grants")
    assert response.status_code == 403


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


def test_grant_change_ggis_get(authenticated_platform_admin_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_platform_admin_client.get(
        url_for("deliver_grant_funding.grant_change_ggis", grant_id=grant.id)
    )
    assert result.status_code == 200
    assert templates_rendered.get("deliver_grant_funding.grant_change_ggis").context.get("grant") == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert "What is the GGIS reference number?" in get_h1_text(soup)


def test_grant_change_name_get(authenticated_grant_admin_client, factories, templates_rendered):
    grant = authenticated_grant_admin_client.grant
    result = authenticated_grant_admin_client.get(url_for("deliver_grant_funding.grant_change_name", grant_id=grant.id))
    assert result.status_code == 200
    assert templates_rendered.get("deliver_grant_funding.grant_change_name").context.get("grant") == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert "What is the name of this grant?" in get_h1_text(soup)


def test_grant_change_description_get(authenticated_grant_admin_client, factories, templates_rendered):
    grant = authenticated_grant_admin_client.grant
    result = authenticated_grant_admin_client.get(
        url_for("deliver_grant_funding.grant_change_description", grant_id=grant.id)
    )
    assert result.status_code == 200
    assert templates_rendered.get("deliver_grant_funding.grant_change_description").context.get("grant") == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert "What is the main purpose of this grant?" in get_h1_text(soup)


def test_grant_change_contact_get(authenticated_grant_admin_client, factories, templates_rendered):
    grant = authenticated_grant_admin_client.grant
    result = authenticated_grant_admin_client.get(
        url_for("deliver_grant_funding.grant_change_contact", grant_id=grant.id)
    )
    assert result.status_code == 200
    assert templates_rendered.get("deliver_grant_funding.grant_change_contact").context.get("grant") == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert "Who is the main contact for this grant?" in get_h1_text(soup)


def test_grant_change_name_post(authenticated_platform_admin_client, factories, templates_rendered, db_session):
    grant = factories.grant.create()
    # Update the name
    form = GrantNameForm()
    form.name.data = "New name"
    result = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_change_name", grant_id=grant.id), data=form.data, follow_redirects=False
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "deliver_grant_funding.grant_details",
        grant_id=grant.id,
    )

    # Check the update is in the database
    grant_from_db = db_session.get(Grant, grant.id)
    assert grant_from_db.name == "New name"


def test_grant_change_contact_post(authenticated_platform_admin_client, factories, templates_rendered, db_session):
    grant = factories.grant.create()
    # Update the name
    form = GrantContactForm()
    form.primary_contact_name.data = "New name"
    form.primary_contact_email.data = "new@email.com"
    result = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_change_contact", grant_id=grant.id), data=form.data, follow_redirects=False
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


def test_grant_change_ggis_post(authenticated_platform_admin_client, factories, templates_rendered, db_session):
    grant = factories.grant.create()
    # Update the name
    form = GrantGGISForm()
    form.has_ggis.data = "yes"
    form.ggis_number.data = "New number"
    result = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_change_ggis", grant_id=grant.id), data=form.data, follow_redirects=False
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "deliver_grant_funding.grant_details",
        grant_id=grant.id,
    )

    # Check the update is in the database
    grant_from_db = db_session.get(Grant, grant.id)
    assert grant_from_db.ggis_number == "New number"


def test_grant_change_description_post(authenticated_platform_admin_client, factories, templates_rendered, db_session):
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


def test_grant_change_name_post_with_errors(authenticated_platform_admin_client, factories, templates_rendered):
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


def test_create_collection_get(authenticated_platform_admin_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_platform_admin_client.get(
        url_for("developers.deliver.setup_collection", grant_id=grant.id),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "What is the name of the collection?"


def test_create_collection_post(authenticated_platform_admin_client, factories, db_session):
    grant = factories.grant.create()
    collection_form = CollectionForm(name="My test collection")
    result = authenticated_platform_admin_client.post(
        url_for("developers.deliver.setup_collection", grant_id=grant.id),
        data=collection_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for("developers.deliver.grant_developers", grant_id=grant.id)

    grant_from_db = db_session.scalars(select(Grant).where(Grant.id == grant.id)).one()
    assert len(grant_from_db.collections) == 1


def test_create_collection_post_duplicate_name(authenticated_platform_admin_client, factories, db_session):
    grant = factories.grant.create()
    factories.collection.create(name="My test collection", grant=grant)
    collection_form = CollectionForm(name="My test collection")
    result = authenticated_platform_admin_client.post(
        url_for("developers.deliver.setup_collection", grant_id=grant.id),
        data=collection_form.data,
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h2_text(soup) == "There is a problem"
    assert len(soup.find_all("a", href="#name")) == 1
    assert soup.find_all("a", href="#name")[0].text.strip() == "Name already in use"


def test_create_section_get(authenticated_platform_admin_client, factories, templates_rendered):
    collection = factories.collection.create()
    result = authenticated_platform_admin_client.get(
        url_for("developers.deliver.add_section", grant_id=collection.grant.id, collection_id=collection.id),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "What is the name of the section?"


def test_create_section_post(authenticated_platform_admin_client, factories, db_session):
    collection = factories.collection.create()
    section_form = SectionForm(title="My test section")
    result = authenticated_platform_admin_client.post(
        url_for("developers.deliver.add_section", grant_id=collection.grant.id, collection_id=collection.id),
        data=section_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.list_sections", grant_id=collection.grant.id, collection_id=collection.id
    )

    collection_from_db = db_session.scalars(select(Collection).where(Collection.id == collection.id)).one()
    assert len(collection_from_db.sections) == 1


def test_create_section_post_duplicate_name(authenticated_platform_admin_client, factories, db_session):
    collection = factories.collection.create()
    factories.section.create(title="My test section", collection=collection)
    section_form = SectionForm(title="My test section")
    result = authenticated_platform_admin_client.post(
        url_for("developers.deliver.add_section", grant_id=collection.grant.id, collection_id=collection.id),
        data=section_form.data,
    )

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h2_text(soup) == "There is a problem"
    assert len(soup.find_all("a", href="#title")) == 1
    assert soup.find_all("a", href="#title")[0].text.strip() == "Title already in use"


def test_create_form_get(authenticated_platform_admin_client, factories, templates_rendered):
    section = factories.section.create()
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.deliver.add_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "Add a form"

    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.deliver.add_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
            form_type="text",
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "What is the name of the form?"


def test_create_form_post(authenticated_platform_admin_client, factories, db_session):
    section = factories.section.create()
    form_form = FormForm(title="My test form")
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.add_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
            form_type="text",
        ),
        data=form_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_section",
        grant_id=section.collection.grant.id,
        collection_id=section.collection.id,
        section_id=section.id,
    )

    section_from_db = db_session.scalars(select(Section).where(Section.id == section.id)).one()
    assert len(section_from_db.forms) == 1


def test_create_form_post_duplicate_name(authenticated_platform_admin_client, factories, db_session):
    section = factories.section.create()
    factories.form.create(title="My test form", section=section)
    form_form = FormForm(title="My test form")
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.add_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
            form_type="text",
        ),
        data=form_form.data,
    )
    assert result.status_code == 200
    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h2_text(soup) == "There is a problem"
    assert len(soup.find_all("a", href="#title")) == 1
    assert soup.find_all("a", href="#title")[0].text.strip() == "Title already in use"


def test_move_section(authenticated_platform_admin_client, factories, db_session):
    collection = factories.collection.create()
    section1 = factories.section.create(collection=collection, order=0)
    section2 = factories.section.create(collection=collection, order=1)

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_section",
            grant_id=collection.grant.id,
            collection_id=collection.id,
            section_id=section1.id,
            direction="down",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.list_sections",
        grant_id=collection.grant.id,
        collection_id=collection.id,
    )

    # Check the order has been updated in the database
    section1_from_db = db_session.scalars(select(Section).where(Section.id == section1.id)).one()
    section2_from_db = db_session.scalars(select(Section).where(Section.id == section2.id)).one()
    assert section1_from_db.order == 1
    assert section2_from_db.order == 0

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_section",
            grant_id=collection.grant.id,
            collection_id=collection.id,
            section_id=section1.id,
            direction="up",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.list_sections",
        grant_id=collection.grant.id,
        collection_id=collection.id,
    )

    # Check the order has been updated in the database
    section1_from_db = db_session.scalars(select(Section).where(Section.id == section1.id)).one()
    section2_from_db = db_session.scalars(select(Section).where(Section.id == section2.id)).one()
    assert section1_from_db.order == 0
    assert section2_from_db.order == 1

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_section",
            grant_id=collection.grant.id,
            collection_id=collection.id,
            section_id=section1.id,
            direction="bad_direction",
        ),
    )
    assert result.status_code == 400


def test_move_form(authenticated_platform_admin_client, factories, db_session):
    section = factories.section.create()
    form1 = factories.form.create(section=section, order=0)
    form2 = factories.form.create(section=section, order=1)
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
            form_id=form1.id,
            direction="down",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_section",
        grant_id=section.collection.grant.id,
        collection_id=section.collection.id,
        section_id=section.id,
    )

    form1_from_db = db_session.scalars(select(Form).where(Form.id == form1.id)).one()
    form2_from_db = db_session.scalars(select(Form).where(Form.id == form2.id)).one()
    assert form1_from_db.order == 1
    assert form2_from_db.order == 0
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
            form_id=form1.id,
            direction="up",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_section",
        grant_id=section.collection.grant.id,
        collection_id=section.collection.id,
        section_id=section.id,
    )

    form1_from_db = db_session.scalars(select(Form).where(Form.id == form1.id)).one()
    form2_from_db = db_session.scalars(select(Form).where(Form.id == form2.id)).one()
    assert form1_from_db.order == 0
    assert form2_from_db.order == 1

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_form",
            grant_id=section.collection.grant.id,
            collection_id=section.collection.id,
            section_id=section.id,
            form_id=form1.id,
            direction="bad_direction",
        ),
    )
    assert result.status_code == 400


def test_move_question(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    question1 = factories.question.create(form=form, order=0)
    question2 = factories.question.create(form=form, order=1)
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question1.id,
            direction="down",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_form",
        grant_id=form.section.collection.grant.id,
        collection_id=form.section.collection.id,
        section_id=form.section.id,
        form_id=form.id,
    )

    question1_from_db = db_session.scalars(select(Question).where(Question.id == question1.id)).one()
    question2_from_db = db_session.scalars(select(Question).where(Question.id == question2.id)).one()
    assert question1_from_db.order == 1
    assert question2_from_db.order == 0

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question1.id,
            direction="up",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_form",
        grant_id=form.section.collection.grant.id,
        collection_id=form.section.collection.id,
        section_id=form.section.id,
        form_id=form.id,
    )

    question1_from_db = db_session.scalars(select(Question).where(Question.id == question1.id)).one()
    question2_from_db = db_session.scalars(select(Question).where(Question.id == question2.id)).one()
    assert question1_from_db.order == 0
    assert question2_from_db.order == 1

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.move_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question1.id,
            direction="bad_direction",
        ),
    )
    assert result.status_code == 400


def test_create_question_choose_type_get(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.deliver.choose_question_type",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "What is the type of the question?"


def test_create_question_choose_type_post(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    wt_form = QuestionTypeForm(question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name)
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.choose_question_type",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.add_question",
        grant_id=form.section.collection.grant.id,
        collection_id=form.section.collection.id,
        section_id=form.section.id,
        form_id=form.id,
        question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
    )


def test_create_question_choose_type_post_error(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    wt_form = QuestionTypeForm()
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.choose_question_type",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 200
    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h2_text(soup) == "There is a problem"
    assert len(soup.find_all("a", href="#question type")) == 1
    assert soup.find_all("a", href="#question type")[0].text.strip() == "Select a question type"


def test_add_text_question_get(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.deliver.add_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "Add question"

    assert (
        soup.find_all("dd", class_="govuk-summary-list__value")[0].text.strip()
        == QuestionDataType.TEXT_SINGLE_LINE.value
    )


def test_add_text_question_post(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    wt_form = QuestionForm(
        question_type=QuestionDataType.TEXT_SINGLE_LINE,
        text="Text question 1",
        hint="some hint text",
        name="question 1",
    )
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.add_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.edit_question",
        grant_id=form.section.collection.grant.id,
        collection_id=form.section.collection.id,
        section_id=form.section.id,
        form_id=form.id,
        question_id=db_session.query(Question).first().id,
    )

    form_from_db = db_session.scalars(select(Form).where(Form.id == form.id)).one()
    assert len(form_from_db.questions) == 1
    assert form_from_db.questions[0].data_type == QuestionDataType.TEXT_SINGLE_LINE


def test_add_text_question_post_duplicate_text(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    factories.question.create(form=form, text="duplicate text")
    wt_form = QuestionForm(
        question_type=QuestionDataType.TEXT_SINGLE_LINE, text="duplicate text", hint="some hint text", name="question 1"
    )
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.add_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h2_text(soup) == "There is a problem"
    assert len(soup.find_all("a", href="#text")) == 1
    assert soup.find_all("a", href="#text")[0].text.strip() == "Text already in use"


def test_edit_question_get(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    question = factories.question.create(form=form, text="Test Question", hint="Test Hint", name="Test Question Name")
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.deliver.edit_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question.id,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "Edit question"


def test_edit_question_post(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    question = factories.question.create(form=form, text="Test Question", hint="Test Hint", name="Test Question Name")
    wt_form = QuestionForm(
        question_type=QuestionDataType.TEXT_SINGLE_LINE,
        text="Updated Question",
        hint="Updated Hint",
        name="Updated Question Name",
    )
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.edit_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question.id,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_form",
        grant_id=form.section.collection.grant.id,
        collection_id=form.section.collection.id,
        section_id=form.section.id,
        form_id=form.id,
    )

    question_from_db = db_session.scalars(select(Question).where(Question.id == question.id)).one()
    assert question_from_db.text == "Updated Question"
    assert question_from_db.hint == "Updated Hint"
    assert question_from_db.name == "Updated Question Name"


def test_grant_setup_intro_get(authenticated_platform_admin_client):
    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_intro"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert get_h1_text(soup) == "Tell us about the grant"


def test_grant_setup_intro_post(authenticated_platform_admin_client):
    intro_form = GenericSubmitForm()
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_intro"), data=intro_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_ggis")


def test_grant_setup_ggis_get_with_session(authenticated_platform_admin_client):
    # Set up session state first
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_ggis"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert get_h1_text(soup) == "Do you have a Government Grants Information System (GGIS) reference number?"


def test_grant_setup_ggis_get_without_session_redirects(authenticated_platform_admin_client):
    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_ggis"))
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_intro")


def test_grant_setup_ggis_post_with_ggis(authenticated_platform_admin_client):
    # Set up session state first
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    ggis_form = GrantGGISForm(has_ggis="yes", ggis_number="GGIS_TEST_123")
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_ggis"), data=ggis_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_name")


def test_grant_setup_ggis_post_no_ggis_redirects_to_required_info(authenticated_platform_admin_client):
    # Set up session state first
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    ggis_form = GrantGGISForm(has_ggis="no")
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_ggis"), data=ggis_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_ggis_required_info")


def test_grant_setup_ggis_required_info_get(authenticated_platform_admin_client):
    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_ggis_required_info"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert "You need to have a GGIS reference number before you can add this grant" in get_h1_text(soup)


def test_grant_setup_name_get_with_session(authenticated_platform_admin_client):
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_name"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert get_h1_text(soup) == "What is the name of this grant?"


def test_grant_setup_name_post(authenticated_platform_admin_client):
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    name_form = GrantNameForm(name="Test Grant Name")
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_name"), data=name_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_description")


def test_grant_setup_description_get_with_session(authenticated_platform_admin_client):
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_description"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert get_h1_text(soup) == "What is the main purpose of this grant?"


def test_grant_setup_description_post_too_long(authenticated_platform_admin_client):
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    long_description = " ".join(["word"] * 201)
    desc_form = GrantDescriptionForm(description=long_description)
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_description"), data=desc_form.data, follow_redirects=False
    )
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert get_h2_text(soup) == "There is a problem"
    assert len(soup.find_all("a", href="#description")) == 1
    assert "Description must be 200 words or fewer" in soup.find_all("a", href="#description")[0].text.strip()


def test_grant_setup_description_post_valid(authenticated_platform_admin_client):
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    desc_form = GrantDescriptionForm(description="A valid description under 200 words.")
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_description"), data=desc_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_contact")


def test_grant_setup_contact_get_with_session(authenticated_platform_admin_client):
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    response = authenticated_platform_admin_client.get(url_for("deliver_grant_funding.grant_setup_contact"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert get_h1_text(soup) == "Who is the main contact for this grant?"


def test_grant_setup_contact_post_valid(authenticated_platform_admin_client):
    # Set up session with required data for grant creation
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {}

    contact_form = GrantContactForm(primary_contact_name="Test Contact", primary_contact_email="test@example.com")
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_contact"), data=contact_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_check_your_answers")


def test_grant_check_your_answers_post_creates_grant(authenticated_platform_admin_client, db_session):
    # Set up session with required data for grant creation
    with authenticated_platform_admin_client.session_transaction() as sess:
        sess["grant_setup"] = {
            "name": "Test Grant",
            "description": "Test description",
            "has_ggis": "yes",
            "ggis_number": "GGIS123",
            "primary_contact_name": "Joe Bloggs",
            "primary_contact_email": "joe.bloggs@gmail.com",
        }

    contact_form = GenericSubmitForm()
    response = authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.grant_setup_check_your_answers"), data=contact_form.data, follow_redirects=False
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


def test_list_users_for_grant_with_platform_admin_and_no_member(
    authenticated_platform_admin_client, templates_rendered, factories, mock_notification_service_calls
):
    grant = factories.grant.create()
    authenticated_platform_admin_client.get(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id))
    users = templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").users
    assert not users


def test_list_users_for_grant_with_platform_admin_check_add_member_button(
    authenticated_platform_admin_client, factories
):
    grant = factories.grant.create()
    response = authenticated_platform_admin_client.get(
        url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id)
    )
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("a", string=lambda text: text and "Add grant team member" in text), (
        "'Add grant team member' button not found"
    )


def test_add_user_to_grant_with_platform_admin_add_another_platform_admin(
    authenticated_platform_admin_client, templates_rendered, factories, mock_notification_service_calls
):
    grant = factories.grant.create()
    current_user = get_current_user()
    authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
        json={"user_email": current_user.email.upper()},
        follow_redirects=True,
    )
    form_errors = templates_rendered.get("deliver_grant_funding.add_user_to_grant").context.get("form").errors
    assert form_errors
    assert "user_email" in form_errors
    assert (
        form_errors["user_email"][0]
        == "This user already exists as a Funding Service admin user so you cannot add them"
    )


def test_add_user_to_grant_with_platform_admin_add_member(
    authenticated_platform_admin_client, templates_rendered, factories, mock_notification_service_calls
):
    grant = factories.grant.create()
    authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
        json={"user_email": "test1@communities.gov.uk"},
        follow_redirects=True,
    )
    invitations = templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").invitations
    assert invitations
    assert len(invitations) == 1


def test_add_user_to_grant_with_platform_admin_add_same_member_again(
    authenticated_platform_admin_client, templates_rendered, factories, mock_notification_service_calls
):
    grant = factories.grant.create()
    user = factories.user.create(email="test1.member@communities.gov.uk")
    factories.user_role.create(user=user, grant=grant, role=RoleEnum.MEMBER)
    authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
        json={"user_email": "Test1.Member@Communities.gov.uk"},
        follow_redirects=True,
    )
    form_errors = templates_rendered.get("deliver_grant_funding.add_user_to_grant").context.get("form").errors
    assert form_errors
    assert "user_email" in form_errors
    assert form_errors["user_email"][0] == f'This user already is a member of "{grant.name}" so you cannot add them'


def test_add_user_to_grant_creates_invitation_for_new_user(
    authenticated_platform_admin_client, db_session, factories, mock_notification_service_calls
):
    grant = factories.grant.create()
    authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
        json={"user_email": "test1@communities.gov.uk"},
        follow_redirects=True,
    )

    usable_invites_from_db = db_session.query(Invitation).where(Invitation.is_usable.is_(True)).all()
    assert len(usable_invites_from_db) == 1
    assert (
        usable_invites_from_db[0].email == "test1@communities.gov.uk"
        and usable_invites_from_db[0].grant_id == grant.id
        and usable_invites_from_db[0].role == RoleEnum.MEMBER
    )


def test_add_user_to_grant_adds_existing_user_no_invitation(
    authenticated_platform_admin_client, db_session, factories, mock_notification_service_calls
):
    grant = factories.grant.create()
    user = factories.user.create(email="test1@communities.gov.uk")
    authenticated_platform_admin_client.post(
        url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
        json={"user_email": "test1@communities.gov.uk"},
        follow_redirects=True,
    )
    usable_invites_from_db = db_session.query(Invitation).where(Invitation.is_usable.is_(True)).all()
    assert not usable_invites_from_db
    assert len(user.roles) == 1
    assert user.roles[0].grant_id == grant.id and user.roles[0].role == RoleEnum.MEMBER


def test_list_users_for_grant_with_member_no_add_member_button(authenticated_grant_member_client, factories):
    grant = factories.grant.create()
    user = get_current_user()
    factories.user_role.create(user=user, role=RoleEnum.MEMBER, grant=grant)
    response = authenticated_grant_member_client.get(
        url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id)
    )
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("a", string=lambda text: text and "Add grant team member" in text) is None


def test_list_users_for_grant_with_not_logged_in_members(
    authenticated_platform_admin_client, factories, templates_rendered
):
    grant = factories.grant.create()
    factories.invitation.create(email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER)

    response = authenticated_platform_admin_client.get(
        url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id)
    )
    soup = BeautifulSoup(response.data, "html.parser")
    assert "Not yet signed in" in soup.h2.text.strip()
    assert "test@communities.gov.uk" in soup.td.text.strip()


def test_list_users_for_grant_with_member(authenticated_grant_member_client, templates_rendered, factories):
    grant = factories.grant.create()
    user = get_current_user()
    factories.user_role.create(user=user, role=RoleEnum.MEMBER, grant=grant)
    authenticated_grant_member_client.get(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id))
    users = templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").users
    assert users
    assert len(users) == 1


def test_accessing_question_page_with_failing_condition_redirects(
    authenticated_platform_admin_client, factories, templates_rendered
):
    question = factories.question.create()
    submission = factories.submission.create(collection=question.form.section.collection)

    response = authenticated_platform_admin_client.get(
        url_for("developers.deliver.ask_a_question", submission_id=submission.id, question_id=question.id),
    )
    assert response.status_code == 200

    # the question should no longer be accessible
    factories.expression.create(question=question, type=ExpressionType.CONDITION, statement="False")

    response = authenticated_platform_admin_client.get(
        url_for("developers.deliver.ask_a_question", submission_id=submission.id, question_id=question.id),
    )
    assert response.status_code == 302
    assert response.location == url_for(
        "developers.deliver.check_your_answers", submission_id=submission.id, form_id=question.form.id
    )
