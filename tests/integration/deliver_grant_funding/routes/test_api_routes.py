import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.deliver_grant_funding.forms import PreviewGuidanceForm


class TestPreviewGuidance:
    @pytest.mark.authenticate_as("person@gmail.com")
    def test_post_unauthorised_if_not_mhclg_email_address(self, authenticated_no_role_client, factories):
        collection = factories.collection.create()

        form = PreviewGuidanceForm(markdown="")
        response = authenticated_no_role_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id), json=form.data
        )
        assert response.status_code == 401
        assert response.json["error"] == "Unauthorised"

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_success_with_mhclg_user(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        form = PreviewGuidanceForm(guidance="## Heading\n\n* list item\n\n[link](https://www.gov.uk)")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id),
            json=form.data,
        )
        assert response.status_code == 200
        assert response.json["guidance_html"] == (
            '<h2 class="govuk-heading-m">Heading</h2>\n'
            '<ul class="govuk-list govuk-list--bullet">\n'
            "<li>list item</li>\n"
            "</ul>\n"
            "<p class='govuk-body'>"
            '<a href="https://www.gov.uk" class="govuk-link govuk-link--no-visited-state">link</a>'
            "</p>\n"
        )

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_interpolates_guidance(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Collection")
        q = factories.question.create(form__collection=collection, form__title="Form", name="my question name")
        form = PreviewGuidanceForm(guidance=f"Test interpolation: (({q.safe_qid}))")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id),
            json=form.data,
        )
        assert response.status_code == 200
        assert response.json["guidance_html"] == (
            "<p class='govuk-body'>Test interpolation: "
            '<span class="app-context-aware-editor--valid-reference">((Collection → Form → my question name))</span>'
            "</p>\n"
        )

    def test_post_with_script_tags_are_escaped(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Collection")
        q = factories.question.create(form__collection=collection, form__title="Form", name="my question name")
        form = PreviewGuidanceForm(guidance=f"<script>alert('bad user input')</script>: (({q.safe_qid}))")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id),
            json=form.data,
        )
        assert response.status_code == 200
        assert response.json["guidance_html"] == (
            "&lt;script&gt;alert(&#x27;bad user input&#x27;)&lt;/script&gt;: "
            '<span class="app-context-aware-editor--valid-reference">((Collection → Form → my question name))</span>\n'
        )


class TestPreviewQuestion:
    @pytest.mark.authenticate_as("person@gmail.com")
    def test_post_unauthorised_if_not_mhclg_email_address(self, authenticated_no_role_client, factories):
        collection = factories.collection.create()

        response = authenticated_no_role_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "TEXT_SINGLE_LINE", "text": "What is your name?"},
        )
        assert response.status_code == 401
        assert response.json["error"] == "Unauthorised"

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_returns_400_without_required_fields(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "TEXT_SINGLE_LINE"},
        )
        assert response.status_code == 400
        assert response.json["errors"] == ["Question text and data type are required"]

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_returns_400_with_invalid_data_type(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "INVALID_TYPE", "text": "Question?"},
        )
        assert response.status_code == 400
        assert response.json["errors"] == ["Invalid question data type"]

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_renders_text_single_line_question(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "TEXT_SINGLE_LINE",
                "text": "What is your name?",
                "hint": "Enter your full name",
                "name": "full_name",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        assert soup.find("label", string=lambda t: t and "What is your name?" in t)
        assert soup.find(string=lambda t: t and "Enter your full name" in t)

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_renders_number_question_with_prefix(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "NUMBER",
                "text": "How much funding?",
                "name": "funding_amount",
                "number_type": "Whole number",
                "prefix": "£",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        assert soup.find("label", string=lambda t: t and "How much funding?" in t)
        prefix_element = soup.find("div", class_="govuk-input__prefix")
        assert prefix_element and "£" in prefix_element.text

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_renders_yes_no_question(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "YES_NO",
                "text": "Do you agree?",
                "name": "agreement",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        legend = soup.find("legend")
        assert legend and "Do you agree?" in legend.get_text()
        labels = soup.find_all("label")
        label_texts = [label.get_text(strip=True) for label in labels]
        assert "Yes" in label_texts
        assert "No" in label_texts

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_renders_radios_question(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "RADIOS",
                "text": "Pick a colour",
                "name": "colour",
                "data_source_items": "Red\nGreen\nBlue",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        legend = soup.find("legend")
        assert legend and "Pick a colour" in legend.get_text()
        labels = soup.find_all("label")
        label_texts = [label.get_text(strip=True) for label in labels]
        assert "Red" in label_texts
        assert "Green" in label_texts
        assert "Blue" in label_texts

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_renders_date_question(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "DATE",
                "text": "When did it start?",
                "name": "start_date",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        legend = soup.find("legend")
        assert legend and "When did it start?" in legend.get_text()

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_includes_section_caption(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        db_form = factories.form.create(collection=collection, title="Project Details")

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "TEXT_SINGLE_LINE",
                "text": "What is the project name?",
                "name": "project_name",
                "form_id": str(db_form.id),
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        caption = soup.find("span", class_="govuk-caption-l")
        assert caption and "Project Details" in caption.text

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_loads_guidance_from_existing_question(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        question = factories.question.create(
            form__collection=collection,
            guidance_heading="Important information",
            guidance_body="Please read this carefully",
            expressions=[],
        )

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": question.data_type.name,
                "text": "Updated question text",
                "name": "updated_name",
                "question_id": str(question.id),
                "form_id": str(question.form_id),
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        heading = soup.find("h1", class_="govuk-heading-l")
        assert heading and "Important information" in heading.text

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_renders_check_answer_button(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "TEXT_SINGLE_LINE", "text": "Your name?", "name": "name"},
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        button = soup.find("button", attrs={"data-check-answer": True})
        assert button and "Check answer" in button.text


class TestPreviewQuestionValidation:
    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_empty_answer_shows_required_field_error(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "TEXT_SINGLE_LINE", "text": "Your name?", "name": "name", "answer": ""},
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        error_summary = soup.find("div", class_="govuk-error-summary")
        assert error_summary
        assert "Enter the name" in error_summary.get_text()

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_valid_answer_shows_no_errors(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "TEXT_SINGLE_LINE", "text": "Your name?", "name": "name", "answer": "Alice"},
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        assert not soup.find("div", class_="govuk-error-summary")

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_invalid_email_shows_format_error(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={"data_type": "EMAIL", "text": "Your email?", "name": "email", "answer": "not-an-email"},
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        error_summary = soup.find("div", class_="govuk-error-summary")
        assert error_summary
        assert "Enter an email address in the correct format" in error_summary.get_text()

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_expression_validation_that_passes(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        question = factories.question.create(
            form__collection=collection,
            data_type=QuestionDataType.NUMBER,
            name="amount",
            expressions=[],
        )
        factories.expression.create(
            question=question,
            created_by=authenticated_grant_member_client.user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({question.safe_qid})) > Decimal('5')",
            context={"question_id": str(question.id), "minimum_value": 5, "minimum_expression": None},
        )

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "NUMBER",
                "text": "Enter amount",
                "name": "amount",
                "number_type": "Whole number",
                "question_id": str(question.id),
                "answer": "10",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        assert not soup.find("div", class_="govuk-error-summary")

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_expression_validation_that_fails(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        question = factories.question.create(
            form__collection=collection,
            data_type=QuestionDataType.NUMBER,
            name="amount",
            expressions=[],
        )
        factories.expression.create(
            question=question,
            created_by=authenticated_grant_member_client.user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({question.safe_qid})) > Decimal('5')",
            context={"question_id": str(question.id), "minimum_value": 5, "minimum_expression": None},
        )

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "NUMBER",
                "text": "Enter amount",
                "name": "amount",
                "number_type": "Whole number",
                "question_id": str(question.id),
                "answer": "3",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        error_summary = soup.find("div", class_="govuk-error-summary")
        assert error_summary
        assert "must be greater than" in error_summary.get_text()

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_expression_referencing_another_question_is_skipped(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        form = factories.form.create(collection=collection)
        other_question = factories.question.create(
            form=form, data_type=QuestionDataType.NUMBER, order=0, name="threshold"
        )
        question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1, name="amount")
        factories.expression.create(
            question=question,
            created_by=authenticated_grant_member_client.user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({question.safe_qid})) > (({other_question.safe_qid}))",
            context={
                "question_id": str(question.id),
                "minimum_value": None,
                "minimum_expression": f"(({other_question.safe_qid}))",
            },
        )

        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_question", collection_id=collection.id),
            json={
                "data_type": "NUMBER",
                "text": "Enter amount",
                "name": "amount",
                "number_type": "Whole number",
                "question_id": str(question.id),
                "answer": "3",
            },
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.json["question_html"], "html.parser")
        assert not soup.find("div", class_="govuk-error-summary")
