from uuid import UUID

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import select

from app.common.data.models import CollectionSchema, Form, Grant, Question, Section
from app.common.data.types import QuestionDataType
from app.deliver_grant_funding.forms import (
    FormForm,
    GrantContactForm,
    GrantDescriptionForm,
    GrantForm,
    GrantGGISForm,
    GrantNameSetupForm,
    GrantSetupIntroForm,
    QuestionForm,
    QuestionTypeForm,
    SchemaForm,
    SectionForm,
)


def test_list_grants(app, authenticated_client, factories, templates_rendered, track_sql_queries):
    factories.grant.create_batch(5)
    with track_sql_queries() as queries:
        result = authenticated_client.get("/grants")
    assert result.status_code == 200
    assert len(templates_rendered[0][1]["grants"]) == 5
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text == "Grants"
    assert len(queries) == 3  # 1) select grants, 2) rollback


@pytest.mark.authenticate_as("test@google.com")
def test_list_grant_requires_mhclg_user(authenticated_client, factories, templates_rendered):
    response = authenticated_client.get("/grants")
    assert response.status_code == 403


def test_view_grant_dashboard(authenticated_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_client.get(url_for("deliver_grant_funding.view_grant", grant_id=grant.id))
    assert result.status_code == 200
    assert templates_rendered[0][1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text == grant.name


def test_view_grant_settings(authenticated_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_client.get(url_for("deliver_grant_funding.grant_settings", grant_id=grant.id))
    assert result.status_code == 200
    assert templates_rendered[0][1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert grant.name in soup.h1.text.strip()
    assert "Settings" in soup.h1.text.strip()


def test_grant_change_name_get(authenticated_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_client.get(url_for("deliver_grant_funding.grant_change_name", grant_id=grant.id))
    assert result.status_code == 200
    template = next(
        template
        for template in templates_rendered
        if template[0].name == "deliver_grant_funding/settings/grant_change_name.html"
    )
    assert template[1]["grant"] == grant
    soup = BeautifulSoup(result.data, "html.parser")
    assert "Change grant name" in soup.h1.text.strip()


def test_grant_change_name_post(authenticated_client, factories, templates_rendered, db_session):
    grant = factories.grant.create()
    # Update the name
    form = GrantForm()
    form.name.data = "New name"
    result = authenticated_client.post(
        url_for("deliver_grant_funding.grant_change_name", grant_id=grant.id), data=form.data, follow_redirects=False
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "deliver_grant_funding.grant_settings",
        grant_id=grant.id,
    )

    # Check the update is in the database
    grant_from_db = db_session.get(Grant, grant.id)
    assert grant_from_db.name == "New name"


def test_grant_change_name_post_with_errors(authenticated_client, factories, templates_rendered):
    grants = factories.grant.create_batch(2)
    # Test error handling on an update
    form = GrantForm(data={"name": grants[1].name})
    result = authenticated_client.post(
        url_for("deliver_grant_funding.grant_change_name", grant_id=grants[0].id),
        data=form.data,
        follow_redirects=False,
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#name")) == 1
    assert soup.find_all("a", href="#name")[0].text.strip() == "Name already in use"


def test_create_collection_get(authenticated_platform_admin_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_platform_admin_client.get(
        url_for("developers.setup_schema", grant_id=grant.id),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "What is the name of the schema?"


def test_create_collection_post(authenticated_platform_admin_client, factories, db_session):
    grant = factories.grant.create()
    collection_form = SchemaForm(name="My test collection")
    result = authenticated_platform_admin_client.post(
        url_for("developers.setup_schema", grant_id=grant.id),
        data=collection_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for("developers.grant_developers_schemas", grant_id=grant.id)

    grant_from_db = db_session.scalars(select(Grant).where(Grant.id == grant.id)).one()
    assert len(grant_from_db.collection_schemas) == 1


def test_create_collection_post_duplicate_name(authenticated_platform_admin_client, factories, db_session):
    grant = factories.grant.create()
    factories.collection_schema.create(name="My test collection", grant=grant)
    collection_form = SchemaForm(name="My test collection")
    result = authenticated_platform_admin_client.post(
        url_for("developers.setup_schema", grant_id=grant.id),
        data=collection_form.data,
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#name")) == 1
    assert soup.find_all("a", href="#name")[0].text.strip() == "Name already in use"


def test_create_section_get(authenticated_platform_admin_client, factories, templates_rendered):
    schema = factories.collection_schema.create()
    result = authenticated_platform_admin_client.get(
        url_for("developers.add_section", grant_id=schema.grant.id, schema_id=schema.id),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "What is the name of the section?"


def test_create_section_post(authenticated_platform_admin_client, factories, db_session):
    schema = factories.collection_schema.create()
    section_form = SectionForm(title="My test section")
    result = authenticated_platform_admin_client.post(
        url_for("developers.add_section", grant_id=schema.grant.id, schema_id=schema.id),
        data=section_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for("developers.list_sections", grant_id=schema.grant.id, schema_id=schema.id)

    collection_from_db = db_session.scalars(select(CollectionSchema).where(CollectionSchema.id == schema.id)).one()
    assert len(collection_from_db.sections) == 1


def test_create_section_post_duplicate_name(authenticated_platform_admin_client, factories, db_session):
    schema = factories.collection_schema.create()
    factories.section.create(title="My test section", collection_schema=schema)
    section_form = SectionForm(title="My test section")
    result = authenticated_platform_admin_client.post(
        url_for("developers.add_section", grant_id=schema.grant.id, schema_id=schema.id),
        data=section_form.data,
    )

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#title")) == 1
    assert soup.find_all("a", href="#title")[0].text.strip() == "Title already in use"


def test_create_form_get(authenticated_platform_admin_client, factories, templates_rendered):
    section = factories.section.create()
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.add_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
            section_id=section.id,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "Add a form"

    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.add_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
            section_id=section.id,
            form_type="text",
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "What is the name of the form?"


def test_create_form_post(authenticated_platform_admin_client, factories, db_session):
    section = factories.section.create()
    form_form = FormForm(title="My test form")
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.add_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
            section_id=section.id,
            form_type="text",
        ),
        data=form_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_section",
        grant_id=section.collection_schema.grant.id,
        schema_id=section.collection_schema.id,
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
            "developers.add_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
            section_id=section.id,
            form_type="text",
        ),
        data=form_form.data,
    )
    assert result.status_code == 200
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#title")) == 1
    assert soup.find_all("a", href="#title")[0].text.strip() == "Title already in use"


def test_move_section(authenticated_platform_admin_client, factories, db_session):
    schema = factories.collection_schema.create()
    section1 = factories.section.create(collection_schema=schema, order=0)
    section2 = factories.section.create(collection_schema=schema, order=1)

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_section",
            grant_id=schema.grant.id,
            schema_id=schema.id,
            section_id=section1.id,
            direction="down",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.list_sections",
        grant_id=schema.grant.id,
        schema_id=schema.id,
    )

    # Check the order has been updated in the database
    section1_from_db = db_session.scalars(select(Section).where(Section.id == section1.id)).one()
    section2_from_db = db_session.scalars(select(Section).where(Section.id == section2.id)).one()
    assert section1_from_db.order == 1
    assert section2_from_db.order == 0

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_section",
            grant_id=schema.grant.id,
            schema_id=schema.id,
            section_id=section1.id,
            direction="up",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.list_sections",
        grant_id=schema.grant.id,
        schema_id=schema.id,
    )

    # Check the order has been updated in the database
    section1_from_db = db_session.scalars(select(Section).where(Section.id == section1.id)).one()
    section2_from_db = db_session.scalars(select(Section).where(Section.id == section2.id)).one()
    assert section1_from_db.order == 0
    assert section2_from_db.order == 1

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_section",
            grant_id=schema.grant.id,
            schema_id=schema.id,
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
            "developers.move_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
            section_id=section.id,
            form_id=form1.id,
            direction="down",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_section",
        grant_id=section.collection_schema.grant.id,
        schema_id=section.collection_schema.id,
        section_id=section.id,
    )

    form1_from_db = db_session.scalars(select(Form).where(Form.id == form1.id)).one()
    form2_from_db = db_session.scalars(select(Form).where(Form.id == form2.id)).one()
    assert form1_from_db.order == 1
    assert form2_from_db.order == 0
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
            section_id=section.id,
            form_id=form1.id,
            direction="up",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_section",
        grant_id=section.collection_schema.grant.id,
        schema_id=section.collection_schema.id,
        section_id=section.id,
    )

    form1_from_db = db_session.scalars(select(Form).where(Form.id == form1.id)).one()
    form2_from_db = db_session.scalars(select(Form).where(Form.id == form2.id)).one()
    assert form1_from_db.order == 0
    assert form2_from_db.order == 1

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_form",
            grant_id=section.collection_schema.grant.id,
            schema_id=section.collection_schema.id,
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
            "developers.move_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question1.id,
            direction="down",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_form",
        grant_id=form.section.collection_schema.grant.id,
        schema_id=form.section.collection_schema.id,
        section_id=form.section.id,
        form_id=form.id,
        back_link="manage_section",
    )

    question1_from_db = db_session.scalars(select(Question).where(Question.id == question1.id)).one()
    question2_from_db = db_session.scalars(select(Question).where(Question.id == question2.id)).one()
    assert question1_from_db.order == 1
    assert question2_from_db.order == 0

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question1.id,
            direction="up",
        ),
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_form",
        grant_id=form.section.collection_schema.grant.id,
        schema_id=form.section.collection_schema.id,
        section_id=form.section.id,
        form_id=form.id,
        back_link="manage_section",
    )

    question1_from_db = db_session.scalars(select(Question).where(Question.id == question1.id)).one()
    question2_from_db = db_session.scalars(select(Question).where(Question.id == question2.id)).one()
    assert question1_from_db.order == 0
    assert question2_from_db.order == 1

    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.move_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
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
            "developers.choose_question_type",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "What is the type of the question?"


def test_create_question_choose_type_post(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    wt_form = QuestionTypeForm(question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name)
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.choose_question_type",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.add_question",
        grant_id=form.section.collection_schema.grant.id,
        schema_id=form.section.collection_schema.id,
        section_id=form.section.id,
        form_id=form.id,
        question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
    )


def test_create_question_choose_type_post_error(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    wt_form = QuestionTypeForm()
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.choose_question_type",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 200
    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#question type")) == 1
    assert soup.find_all("a", href="#question type")[0].text.strip() == "Select a question type"


def test_add_text_question_get(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.add_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "Add question"

    assert (
        soup.find_all("dd", class_="govuk-summary-list__value")[0].text.strip()
        == QuestionDataType.TEXT_SINGLE_LINE.value
    )


def test_add_text_question_post(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    wt_form = QuestionForm(text="Text question 1", hint="some hint text", name="question 1")
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.add_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_form",
        grant_id=form.section.collection_schema.grant.id,
        schema_id=form.section.collection_schema.id,
        section_id=form.section.id,
        form_id=form.id,
        back_link="manage_section",
    )

    form_from_db = db_session.scalars(select(Form).where(Form.id == form.id)).one()
    assert len(form_from_db.questions) == 1
    assert form_from_db.questions[0].data_type == QuestionDataType.TEXT_SINGLE_LINE


def test_add_text_question_post_duplicate_text(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    factories.question.create(form=form, text="duplicate text")
    wt_form = QuestionForm(text="duplicate text", hint="some hint text", name="question 1")
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.add_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_data_type=QuestionDataType.TEXT_SINGLE_LINE.name,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"
    assert len(soup.find_all("a", href="#text")) == 1
    assert soup.find_all("a", href="#text")[0].text.strip() == "Text already in use"


def test_edit_question_get(authenticated_platform_admin_client, factories):
    form = factories.form.create()
    question = factories.question.create(form=form, text="Test Question", hint="Test Hint", name="Test Question Name")
    result = authenticated_platform_admin_client.get(
        url_for(
            "developers.edit_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question.id,
        ),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert soup.h1.text.strip() == "Edit question"


def test_edit_question_post(authenticated_platform_admin_client, factories, db_session):
    form = factories.form.create()
    question = factories.question.create(form=form, text="Test Question", hint="Test Hint", name="Test Question Name")
    wt_form = QuestionForm(text="Updated Question", hint="Updated Hint", name="Updated Question Name")
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.edit_question",
            grant_id=form.section.collection_schema.grant.id,
            schema_id=form.section.collection_schema.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=question.id,
        ),
        data=wt_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.manage_form",
        grant_id=form.section.collection_schema.grant.id,
        schema_id=form.section.collection_schema.id,
        section_id=form.section.id,
        form_id=form.id,
        back_link="manage_section",
    )

    question_from_db = db_session.scalars(select(Question).where(Question.id == question.id)).one()
    assert question_from_db.text == "Updated Question"
    assert question_from_db.hint == "Updated Hint"
    assert question_from_db.name == "Updated Question Name"


def test_grant_setup_flow_with_ggis_and_description_error(authenticated_client, db_session, templates_rendered):
    # 1. Intro page
    response = authenticated_client.get(url_for("deliver_grant_funding.grant_setup_intro"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.h1.text.strip() == "Tell us about the grant"

    intro_form = GrantSetupIntroForm()
    response = authenticated_client.post(
        url_for("deliver_grant_funding.grant_setup_intro"), data=intro_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_ggis")

    # 2. GGIS page
    response = authenticated_client.get(response.location)  # Follow redirect
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.h1.text.strip() == "Do you have a Government Grants Information System (GGIS) reference number?"

    ggis_data = "GGIS_COMPREHENSIVE_TEST"
    ggis_form = GrantGGISForm(has_ggis="yes", ggis_number=ggis_data)
    response = authenticated_client.post(
        url_for("deliver_grant_funding.grant_setup_ggis"), data=ggis_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_name")

    # 3. Name page
    response = authenticated_client.get(response.location)  # Follow redirect
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.h1.text.strip() == "What is the name of this grant?"

    grant_name = "Comprehensive Grant Setup Test"
    name_form = GrantNameSetupForm(name=grant_name)
    response = authenticated_client.post(
        url_for("deliver_grant_funding.grant_setup_name"), data=name_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_description")

    # 4. Description page - initial GET
    response = authenticated_client.get(response.location)  # Follow redirect
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.h1.text.strip() == "What is the main purpose of this grant?"

    # 4a. Description page - POST with error (too many words)
    long_description = " ".join(["word"] * 201)  # 201 words
    invalid_desc_form = GrantDescriptionForm(description=long_description)
    response = authenticated_client.post(
        url_for("deliver_grant_funding.grant_setup_description"), data=invalid_desc_form.data, follow_redirects=False
    )
    assert response.status_code == 200  # Should re-render the page due to validation error
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.h2.text.strip() == "There is a problem"  # Check for error summary

    expected_error_message = "Description must be 200 words or fewer."
    error_link = soup.find("a", href="#description")
    assert error_link is not None, "Error link for description not found in summary"
    assert expected_error_message in error_link.text.strip()

    field_error_message = soup.find("p", {"id": "description-error"})
    assert field_error_message is not None, "Error message for description field not found"
    assert expected_error_message in field_error_message.text.strip()

    # 4b. Description page - POST with valid data
    valid_grant_description = (
        "This is a valid description for the comprehensive test, well within the two hundred word limit."
    )
    valid_desc_form = GrantDescriptionForm(description=valid_grant_description)
    response = authenticated_client.post(
        url_for("deliver_grant_funding.grant_setup_description"), data=valid_desc_form.data, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.location == url_for("deliver_grant_funding.grant_setup_contact")

    # 5. Contact page & Submission
    response = authenticated_client.get(response.location)  # Follow redirect
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.h1.text.strip() == "Who is the main contact for this grant?"

    contact_name = "Comprehensive Test Contact"
    contact_email = "comprehensive@example.com"
    contact_form = GrantContactForm(primary_contact_name=contact_name, primary_contact_email=contact_email)
    response = authenticated_client.post(
        url_for("deliver_grant_funding.grant_setup_contact"), data=contact_form.data, follow_redirects=False
    )
    assert response.status_code == 302

    grant_id_str = response.location.split("/")[-1]
    grant_id = UUID(grant_id_str)
    assert response.location == url_for("deliver_grant_funding.view_grant", grant_id=grant_id)

    # Verify grant in DB
    grant_from_db = db_session.get(Grant, grant_id)
    assert grant_from_db is not None
    assert grant_from_db.name == grant_name
    assert grant_from_db.ggis_number == ggis_data
    assert grant_from_db.description == valid_grant_description
    assert grant_from_db.primary_contact_name == contact_name
    assert grant_from_db.primary_contact_email == contact_email

    # Verify session is cleared
    with authenticated_client.session_transaction() as sess:
        assert "grant_setup" not in sess
