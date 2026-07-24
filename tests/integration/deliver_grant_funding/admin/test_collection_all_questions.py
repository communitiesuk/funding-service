import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.interfaces.collections import add_component_condition, add_component_validation
from app.common.data.types import QuestionDataType, QuestionPresentationOptions
from app.common.expressions.managed import GreaterThan, IsYes
from app.common.expressions.references import ExpressionReference, InterpolationStatement
from app.extensions import db

PER_QUESTION_GUIDANCE = "Include your project aims and expected outcomes"
GROUP_GUIDANCE = "Only complete this section if you have match funding"
QUESTION_HINT = "Roughly 200 words is plenty"


def _build_collection(factories, user):
    """A collection exercising every kind of detail: hint, settings, options, groups, conditions,
    guidance and validation."""
    form = factories.form.create(title="Project details")

    factories.question.create(
        form=form,
        order=0,
        data_type=QuestionDataType.TEXT_MULTI_LINE,
        text="Describe your project",
        hint=InterpolationStatement(QUESTION_HINT),
        presentation_options=QuestionPresentationOptions(word_limit=200),
        guidance_body=InterpolationStatement(PER_QUESTION_GUIDANCE),
    )
    favourite_colour = factories.question.create(
        form=form, order=1, data_type=QuestionDataType.YES_NO, text="Do you have a favourite colour?"
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

    group = factories.group.create(
        form=form,
        order=4,
        name="Match funding",
        add_another=True,
        guidance_body=InterpolationStatement(GROUP_GUIDANCE),
    )
    conditional_question = factories.question.create(
        form=form, parent=group, text="How much match funding do you have?"
    )
    add_component_condition(
        component=conditional_question,
        user=user,
        evaluatable_expression=IsYes(subject_reference=ExpressionReference.from_question(favourite_colour)),
    )

    # The condition/validation helpers flush but don't commit; commit so the read-only page request
    # under test starts from a clean session.
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

    def test_page_lists_sections_questions_groups_and_options(self, authenticated_platform_admin_client, factories):
        collection, radios = _build_collection(factories, authenticated_platform_admin_client.user)

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Page furniture
        assert "View all questions" in text
        assert collection.name in text
        assert "Project details" in text  # section heading

        # Questions and a nested group + its question always show
        assert "Describe your project" in text
        assert "Match funding" in text
        assert "How much match funding do you have?" in text

        # Radio options are listed out at every level
        for item in radios.data_source.items:
            assert item.label in text

        # Download button points at the PDF route (with the current detail level appended)
        pdf_path = url_for("collection.all_questions_pdf", collection_id=collection.id)
        assert soup.select_one(f'a[href^="{pdf_path}"]')

    def test_default_view_shows_every_category(self, authenticated_platform_admin_client, factories):
        collection, _ = _build_collection(factories, authenticated_platform_admin_client.user)

        # No query args: a fresh visit shows every category of information.
        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        text = soup.get_text(" ", strip=True)

        assert QUESTION_HINT in text  # hint text
        assert "(200 words)" in text  # question settings
        assert "Can be added more than once" in text  # group repeat indicator
        assert PER_QUESTION_GUIDANCE in text and GROUP_GUIDANCE in text  # guidance
        assert soup.select(".app-all-questions-condition")  # conditions
        assert soup.select(".app-all-questions-validation")  # validations

    def test_guidance_is_rendered_as_markdown_fenced_between_rules(
        self, authenticated_platform_admin_client, factories
    ):
        form = factories.form.create(title="Project details")
        factories.question.create(
            form=form,
            order=0,
            data_type=QuestionDataType.TEXT_MULTI_LINE,
            text="Describe your project",
            guidance_body=InterpolationStatement("## Guidance heading\n\nFollow the steps carefully"),
        )
        db.session.commit()
        collection = form.collection

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        guidance = soup.select_one(".app-all-questions-guidance")
        assert guidance is not None

        # Guidance markdown is rendered, not shown as raw text: its "##" heading becomes a styled heading.
        heading = guidance.select_one("h2.govuk-heading-m")
        assert heading is not None and heading.get_text(strip=True) == "Guidance heading"
        assert "## Guidance heading" not in soup.get_text()

        # It is fenced between horizontal rules so its own headings don't compete with the page structure.
        previous_hr = guidance.find_previous_sibling("hr")
        next_hr = guidance.find_next_sibling("hr")
        assert previous_hr is not None and "govuk-section-break" in previous_hr.get("class", [])
        assert next_hr is not None and "govuk-section-break" in next_hr.get("class", [])

    def test_filtering_to_a_single_category_hides_the_rest(self, authenticated_platform_admin_client, factories):
        collection, _ = _build_collection(factories, authenticated_platform_admin_client.user)

        # Applied filters showing only conditions: everything else is hidden.
        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id, filtered=1, show="conditions")
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Question and group text still show - only the extra detail is filtered.
        assert "Describe your project" in text
        assert "How much match funding do you have?" in text

        assert soup.select(".app-all-questions-condition")  # the one chosen category
        assert QUESTION_HINT not in text
        assert "(200 words)" not in text
        assert PER_QUESTION_GUIDANCE not in text
        assert not soup.select(".app-all-questions-validation")

    def test_clearing_all_filters_shows_only_the_bare_questions(self, authenticated_platform_admin_client, factories):
        collection, _ = _build_collection(factories, authenticated_platform_admin_client.user)

        # The sentinel with no selection ("Clear filters") shows nothing but the questions themselves.
        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id, filtered=1)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        text = soup.get_text(" ", strip=True)

        assert "Describe your project" in text
        assert QUESTION_HINT not in text
        assert "(200 words)" not in text
        assert PER_QUESTION_GUIDANCE not in text
        assert not soup.select(".app-all-questions-condition")
        assert not soup.select(".app-all-questions-validation")

    def test_moj_filter_component_and_selected_tags(self, authenticated_platform_admin_client, factories):
        collection, _ = _build_collection(factories, authenticated_platform_admin_client.user)

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions", collection_id=collection.id, filtered=1, show="hint")
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        # The MOJ filter component and its toggle-button target are present.
        assert soup.select_one('[data-module="moj-filter"]')
        assert soup.select_one(".moj-action-bar__filter")

        # Exactly one "selected filter" tag (for the single chosen category) plus a clear link.
        tags = soup.select(".moj-filter__tag")
        assert len(tags) == 1
        assert "Hint text" in tags[0].get_text(" ", strip=True)
        clear_url = url_for("collection.all_questions", collection_id=collection.id, filtered=1)
        clear_link = soup.select_one(f'a[href="{clear_url}"]')
        assert clear_link and clear_link.get_text(strip=True) == "Clear filters"

        # The toggle button is initialised server-side with the active-filter count.
        assert soup.select_one('[data-module="moj-filter"]').get("data-active-filter-count") == "1"

    def test_references_are_highlighted_labels_on_web_but_underlined_names_in_pdf(
        self, authenticated_platform_admin_client, factories, mocker
    ):
        form = factories.form.create(title="About your project")
        project_name = factories.question.create(
            form=form, order=0, data_type=QuestionDataType.TEXT_SINGLE_LINE, name="Project name", text="Project name"
        )
        # A later question whose text embeds a reference to the earlier "Project name" question.
        factories.question.create(
            form=form,
            order=1,
            data_type=QuestionDataType.TEXT_MULTI_LINE,
            text=InterpolationStatement(f"Describe {ExpressionReference.from_question(project_name).wrapped}"),
        )
        db.session.commit()
        collection = form.collection

        # Web page: the reference is highlighted and shows its full "collection → section → question" label.
        web = authenticated_platform_admin_client.get(url_for("collection.all_questions", collection_id=collection.id))
        assert web.status_code == 200
        web_soup = BeautifulSoup(web.data, "html.parser")
        highlighted = web_soup.select_one(".app-context-aware-editor--valid-reference")
        assert highlighted is not None
        assert highlighted.get_text() == f"(({project_name.data_reference_label}))"
        assert "→" in highlighted.get_text()  # the full label path, not just the question name
        assert not web_soup.select("u")  # the web page does not use plain underlines

        # PDF: the reference is a plain underlined question name - no brackets, path or highlight span.
        render_pdf = mocker.patch("app.deliver_grant_funding.admin.entities.render_pdf", return_value=b"%PDF-1.4 fake")
        pdf = authenticated_platform_admin_client.get(
            url_for("collection.all_questions_pdf", collection_id=collection.id)
        )
        assert pdf.status_code == 200
        printed_html = render_pdf.call_args.args[0]
        assert "<u>Project name</u>" in printed_html
        assert "app-context-aware-editor--valid-reference" not in printed_html
        assert project_name.data_reference_label not in printed_html  # no full label / brackets leak through

    def test_pdf_download_honours_the_active_filters(self, authenticated_platform_admin_client, factories, mocker):
        collection, _ = _build_collection(factories, authenticated_platform_admin_client.user)

        render_pdf = mocker.patch("app.deliver_grant_funding.admin.entities.render_pdf", return_value=b"%PDF-1.4 fake")

        response = authenticated_platform_admin_client.get(
            url_for("collection.all_questions_pdf", collection_id=collection.id, filtered=1, show="validations")
        )

        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert "all_questions" in response.headers["Content-Disposition"]

        # The printable HTML was built from the same content and honours the active filters.
        render_pdf.assert_called_once()
        printed_html = render_pdf.call_args.args[0]
        assert "Describe your project" in printed_html
        assert "app-all-questions-validation" in printed_html
        assert "app-all-questions-condition" not in printed_html
