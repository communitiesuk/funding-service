import pytest
from bs4 import BeautifulSoup
from flask import render_template_string

from app.common.collections.runner import FormRunner
from app.common.data.types import (
    QuestionDataType,
)
from app.common.helpers.collections import SubmissionHelper


class TestCollectionQuestionMacro:
    def test_the_next_test_exhausts_QuestionDataType(self):
        assert len(QuestionDataType) == 9, (
            "If this test breaks, tweak the number and update "
            "`test_collection_question_renders_and_interpolates_text_and_hint_and_guidance` accordingly."
        )

    @pytest.mark.parametrize("question_type", list(QuestionDataType))
    def test_collection_question_renders_and_interpolates_text_and_hint_and_guidance(
        self, authenticated_grant_admin_client, factories, question_type
    ):
        reference_question = factories.question.create(
            data_type=question_type.TEXT_SINGLE_LINE,
            text="Reference Value",
            form__collection__grant=authenticated_grant_admin_client.grant,
        )
        ref_qid = reference_question.safe_qid

        test_question_text = f"Test question for {question_type.value} with reference (({ref_qid}))"
        test_hint_text = "Test hint: referenced value is (({reference_qid}))".format(reference_qid=ref_qid)
        test_guidance_heading_text = "Guidance for (({reference_qid}))".format(reference_qid=ref_qid)
        test_guidance_body_text = "Test guidance: the reference answer is (({reference_qid}))".format(
            reference_qid=ref_qid
        )

        main_question = factories.question.create(
            data_type=question_type,
            text=test_question_text,
            hint=test_hint_text,
            guidance_heading=test_guidance_heading_text,
            guidance_body=test_guidance_body_text,
            form__collection=reference_question.form.collection,  # Same collection for interpolation context
        )

        submission = factories.submission.create(
            collection=reference_question.form.collection, created_by=authenticated_grant_admin_client.user
        )

        reference_answer_value = "Interpolated Text Value"
        submission_data = {str(reference_question.id): reference_answer_value}
        submission.data = submission_data

        template_content = """
        {% from "common/macros/collections.html" import collection_question with context %}
        {{ collection_question(runner) }}
        """
        rendered_html = render_template_string(
            template_content, runner=FormRunner(SubmissionHelper.load(submission.id), question=main_question)
        )

        soup = BeautifulSoup(rendered_html, "html.parser")
        page_text = soup.get_text()

        expected_question_text = f"Test question for {question_type.value} with reference {reference_answer_value}"
        expected_hint_text = f"Test hint: referenced value is {reference_answer_value}"
        expected_guidance_heading = f"Guidance for {reference_answer_value}"
        expected_guidance_body = f"Test guidance: the reference answer is {reference_answer_value}"

        assert expected_question_text in page_text
        assert expected_hint_text in page_text
        assert expected_guidance_heading in page_text
        assert expected_guidance_body in page_text
        assert f"(({ref_qid}))" not in page_text
