import csv
from io import StringIO

from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import select

from app import QuestionDataType, SubmissionModeEnum
from app.common.data.models import Collection, Expression, Form, Grant, Question, Section
from app.common.data.types import ExpressionType
from app.common.expressions.managed import AnyOf
from app.deliver_grant_funding.forms import CollectionForm, FormForm, QuestionForm, QuestionTypeForm, SectionForm
from tests.utils import get_h1_text, get_h2_text, get_soup_text


def test_create_collection_get(authenticated_platform_admin_client, factories, templates_rendered):
    grant = factories.grant.create()
    result = authenticated_platform_admin_client.get(
        url_for("developers.deliver.setup_collection", grant_id=grant.id),
    )
    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h1_text(soup) == "What is the name of this monitoring report?"


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
    assert get_h1_text(soup) == "Split form into sections"


def test_create_section_post(authenticated_platform_admin_client, factories, db_session):
    collection = factories.collection.create()
    section_form = SectionForm(title="My test section")
    result = authenticated_platform_admin_client.post(
        url_for("developers.deliver.add_section", grant_id=collection.grant.id, collection_id=collection.id),
        data=section_form.data,
    )
    assert result.status_code == 302
    assert result.location == url_for(
        "developers.deliver.manage_collection_tasks", grant_id=collection.grant.id, collection_id=collection.id
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
    assert get_h1_text(soup) == "Add a task"

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
    assert get_h1_text(soup) == "What is the name of the task?"


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
        "developers.deliver.manage_collection_tasks",
        grant_id=section.collection.grant.id,
        collection_id=section.collection.id,
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
    collection = factories.collection.create(default_section=False)
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
        "developers.deliver.manage_collection_tasks",
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
        "developers.deliver.manage_collection_tasks",
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
        "developers.deliver.manage_collection_tasks",
        grant_id=section.collection.grant.id,
        collection_id=section.collection.id,
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
        "developers.deliver.manage_collection_tasks",
        grant_id=section.collection.grant.id,
        collection_id=section.collection.id,
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
        "developers.deliver.manage_form_questions",
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
        "developers.deliver.manage_form_questions",
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
    assert get_h1_text(soup) == "What is the type of question?"


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
    assert len(soup.find_all("a", href="#question_data_type")) == 1
    assert soup.find_all("a", href="#question_data_type")[0].text.strip() == "Select a question type"


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
        "developers.deliver.manage_form_questions",
        grant_id=form.section.collection.grant.id,
        collection_id=form.section.collection.id,
        section_id=form.section.id,
        form_id=form.id,
    )

    question_from_db = db_session.scalars(select(Question).where(Question.id == question.id)).one()
    assert question_from_db.text == "Updated Question"
    assert question_from_db.hint == "Updated Hint"
    assert question_from_db.name == "Updated Question Name"


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


def test_download_csv_export(authenticated_platform_admin_client, factories, db_session):
    # Create a grant and a collection
    grant = factories.grant.create()
    collection = factories.collection.create(
        grant=grant,
        create_completed_submissions_each_question_type__test=3,
        create_completed_submissions_each_question_type__use_random_data=True,
    )

    response = authenticated_platform_admin_client.get(
        url_for(
            "developers.deliver.export_submissions_for_collection",
            collection_id=collection.id,
            submission_mode=SubmissionModeEnum.TEST,
            export_format="csv",
        )
    )

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"] == f'attachment; filename="{collection.name} - TEST.csv"'

    csv_content = response.data.decode("utf-8")
    reader = csv.DictReader(StringIO(csv_content))

    assert reader.fieldnames == [
        "Submission reference",
        "Created by",
        "Created at",
        "[Export test form] Your name",
        "[Export test form] Your quest",
        "[Export test form] Airspeed velocity",
        "[Export test form] Best option",
        "[Export test form] Like cheese",
        "[Export test form] Email address",
        "[Export test form] Website address",
        "[Export test form] Favourite cheeses",
    ]
    rows = list(reader)
    assert len(rows) == 3


def test_edit_question_post_raises_referenced_data_items_exception(
    authenticated_platform_admin_client, factories, db_session
):
    form = factories.form.create()
    referenced_question = factories.question.create(form=form, data_type=QuestionDataType.RADIOS)
    dependent_question = factories.question.create(
        form=form,
        data_type=QuestionDataType.TEXT_SINGLE_LINE,
        expressions=[
            Expression.from_managed(
                AnyOf(
                    question_id=referenced_question.id,
                    items=[
                        {
                            "key": referenced_question.data_source.items[0].key,
                            "label": referenced_question.data_source.items[0].label,
                        }
                    ],
                ),
                factories.user.create(),
            )
        ],
    )
    wt_form = QuestionForm(
        question_type=QuestionDataType.TEXT_SINGLE_LINE,
        text="Updated Question",
        hint="Updated Hint",
        name="Updated Question Name",
        data_source_items="New option 1\nUpdated option 2\nChanged option 3",
    )
    result = authenticated_platform_admin_client.post(
        url_for(
            "developers.deliver.edit_question",
            grant_id=form.section.collection.grant.id,
            collection_id=form.section.collection.id,
            section_id=form.section.id,
            form_id=form.id,
            question_id=referenced_question.id,
        ),
        data=wt_form.data,
        follow_redirects=True,
    )

    assert result.status_code == 200

    soup = BeautifulSoup(result.data, "html.parser")
    assert get_h2_text(soup) == "Error"
    assert "You cannot delete or change an option that other questions depend on" in get_soup_text(soup, "p")
    assert f"Depends on the options: {referenced_question.data_source.items[0].label}" in [
        p.text for p in soup.find_all("p")
    ]
    assert soup.find_all("a", class_="govuk-notification-banner__link")[0].text.strip() == dependent_question.text
