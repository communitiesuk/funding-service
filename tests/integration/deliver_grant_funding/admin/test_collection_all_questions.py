import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.interfaces.collections import add_component_condition, add_component_validation
from app.common.data.types import QuestionDataType, QuestionPresentationOptions
from app.common.expressions.managed import GreaterThan, IsYes
from app.common.expressions.references import ExpressionReference, InterpolationStatement
from app.extensions import db


def _build_collection(factories, user):
    form = factories.form.create(title="Project details")

    factories.question.create(
        form=form,
        order=0,
        data_type=QuestionDataType.TEXT_MULTI_LINE,
        text="Describe your project",
        hint=InterpolationStatement("Roughly 200 words is plenty"),
        presentation_options=QuestionPresentationOptions(word_limit=200),
        guidance_body=InterpolationStatement("## Guidance heading\n\nInclude your project aims"),
    )
    favourite_colour = factories.question.create(
        form=form,
        order=1,
        data_type=QuestionDataType.YES_NO,
        name="Favourite colour",
        text="Do you have a favourite colour?",
    )
    radios = factories.question.create(form=form, order=2, data_type=QuestionDataType.RADIOS, text="Pick an option")

    funding = factories.question.create(
        form=form, order=3, data_type=QuestionDataType.NUMBER, text="How much funding do you need?"
    )
    add_component_validation(
        component=funding,
        user=user,
        evaluatable_expression=GreaterThan(
            subject_reference=ExpressionReference.from_question(funding), minimum_value=100
        ),
    )

    group = factories.group.create(form=form, order=4, name="Match funding", add_another=True)
    conditional_question = factories.question.create(
        form_id=form.id, parent=group, text="How much match funding do you have?"
    )
    add_component_condition(
        component=conditional_question,
        user=user,
        evaluatable_expression=IsYes(subject_reference=ExpressionReference.from_question(favourite_colour)),
    )
    db.session.commit()

    return form.collection, radios


class TestCollectionAllQuestions:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_access_control(self, client_fixture, expected_code, request, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create()

        response = client.get(url_for("collection.all_questions", collection_id=collection.id))

        assert response.status_code == expected_code

    def test_collection_edit_page_links_to_all_questions(self, authenticated_platform_admin_client, factories):
        collection = factories.collection.create()

        response = authenticated_platform_admin_client.get(url_for("collection.edit_view", id=collection.id))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        all_questions_url = url_for("collection.all_questions", collection_id=collection.id)
        assert soup.select_one(f'a[href="{all_questions_url}"]')

    def test_page_lists_questions_and_their_details(self, authenticated_platform_admin_client, factories):
        collection, radios = _build_collection(factories, authenticated_platform_admin_client.user)

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        text = soup.get_text(" ", strip=True)

        assert "Project details" in text
        assert "Describe your project (200 words)" in text
        assert "Roughly 200 words is plenty" in text
        assert "Do you have a favourite colour? (Yes or no)" in text
        assert "Match funding Can be added more than once" in text
        assert "How much match funding do you have?" in text
        assert "Shown if “yes” to 2 (Favourite colour)" in text
        for item in radios.data_source.items:
            assert item.label in text

        assert soup.find("h2", class_="govuk-heading-m", string="Guidance heading")
        assert "## Guidance heading" not in text

        assert "The answer must be greater than 100" not in text
        assert "(A number)" not in text

        pdf_url = url_for("collection.all_questions_pdf", collection_id=collection.id)
        assert soup.select_one(f'a[href="{pdf_url}"]')

    def test_numbering_continues_across_sections_and_nested_items_are_bulleted(
        self, authenticated_platform_admin_client, factories
    ):
        collection = factories.collection.create()
        section_one = factories.form.create(collection=collection, order=0, title="Project details")
        section_two = factories.form.create(collection=collection, order=1, title="Match funding")

        factories.question.create(form=section_one, order=0, text="Describe your project")
        group = factories.group.create(form=section_one, order=1, name="Costs")
        factories.question.create(form_id=section_one.id, parent=group, order=0, text="What are your staff costs?")
        factories.question.create(form=section_two, order=0, text="Who else is funding this?")
        db.session.commit()

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        numbered_lists = soup.select("ol.govuk-list--number")
        assert [list_.get("start") for list_ in numbered_lists] == ["1", "3"]

        nested_list = numbered_lists[0].select_one("li ul.govuk-list--bullet")
        assert nested_list is not None
        assert nested_list.get_text(" ", strip=True) == "What are your staff costs?"

    def test_references_are_underlined_question_names(self, authenticated_platform_admin_client, factories):
        form = factories.form.create(title="About your project")
        project_name = factories.question.create(form=form, order=0, name="Project name", text="Project name")
        factories.question.create(
            form=form,
            order=1,
            text=InterpolationStatement(f"Describe {ExpressionReference.from_question(project_name).wrapped}"),
        )
        db.session.commit()

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=form.collection.id)
        )

        assert response.status_code == 200
        assert "Describe <u>Project name</u>" in response.text

    def test_pdf_download(self, authenticated_platform_admin_client, factories, mocker):
        collection, _ = _build_collection(factories, authenticated_platform_admin_client.user)
        render_pdf = mocker.patch("app.deliver_grant_funding.admin.entities.render_pdf", return_value=b"%PDF-1.4 fake")

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions_pdf", collection_id=collection.id)
        )

        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert "all_questions" in response.headers["Content-Disposition"]
        printed_html = render_pdf.call_args.args[0]
        assert "Describe your project (200 words)" in printed_html
        assert "Shown if “yes” to 2 (Favourite colour)" in printed_html
