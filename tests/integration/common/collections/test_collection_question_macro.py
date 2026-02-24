import pytest
from bs4 import BeautifulSoup
from flask import render_template_string

from app.common.collections.runner import FormRunner
from app.common.collections.types import FileUploadAnswer
from app.common.data.types import (
    FileUploadTypes,
    MaximumFileSize,
    QuestionDataOptions,
    QuestionDataType,
)
from app.common.helpers.collections import SubmissionHelper
from tests.utils import get_h1_text


class TestCollectionQuestionMacro:
    def test_the_next_test_exhausts_QuestionDataType(self):
        assert len(QuestionDataType) == 10, (
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
        test_hint_text = f"Test hint: referenced value is (({ref_qid}))"
        test_guidance_heading_text = "Guidance for ((2))"
        test_guidance_body_text = f"Test guidance: the reference answer is (({ref_qid}))"

        main_question = factories.question.create(
            data_type=question_type,
            text=test_question_text,
            hint=test_hint_text,
            guidance_heading=test_guidance_heading_text,
            guidance_body=test_guidance_body_text,
            form=reference_question.form,  # Same collection for interpolation context
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
        expected_guidance_heading = "Guidance for ((2))"  # does not get interpolated currently
        expected_guidance_body = f"Test guidance: the reference answer is {reference_answer_value}"

        assert expected_question_text in page_text
        assert expected_hint_text in page_text
        assert expected_guidance_heading in page_text
        assert expected_guidance_body in page_text
        assert f"(({ref_qid}))" not in page_text

    def test_collection_question_file_upload_shows_supported_files(self, authenticated_grant_admin_client, factories):
        supported_file_types = [
            FileUploadTypes.PDF,
            FileUploadTypes.IMAGE,
        ]
        unsupported_file_types = [t for t in FileUploadTypes if t not in supported_file_types]
        question = factories.question.create(
            data_type=QuestionDataType.FILE_UPLOAD,
            text="Test file upload question",
            data_options=QuestionDataOptions(
                file_types_supported=supported_file_types, maximum_file_size=MaximumFileSize.LARGE
            ),
            form__collection__grant=authenticated_grant_admin_client.grant,
        )

        template_content = """
        {% from "common/macros/collections.html" import collection_question with context %}
        {{ collection_question(runner) }}
        """
        rendered_html = render_template_string(
            template_content,
            runner=FormRunner(
                SubmissionHelper.load(factories.submission.create(collection=question.form.collection).id),
                question=question,
            ),
        )

        soup = BeautifulSoup(rendered_html, "html.parser")
        page_text = soup.get_text()

        for file_type in supported_file_types:
            assert file_type.value in page_text
            for extension in file_type.extensions:
                assert extension in page_text

        for file_type in unsupported_file_types:
            assert file_type.value not in page_text
            for extension in file_type.extensions:
                assert extension not in page_text

        assert "Your file must be smaller than 100MB" in page_text

    def test_collection_question_clear_answer(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            data_type=QuestionDataType.FILE_UPLOAD,
            text="Test question",
            form__collection__grant=authenticated_grant_admin_client.grant,
        )

        submission = factories.submission.create(
            collection=question.form.collection,
            created_by=authenticated_grant_admin_client.user,
            data={
                str(question.id): FileUploadAnswer(
                    filename="test-file.pdf", size=0, mime_type="application/pdf"
                ).get_value_for_submission()
            },
        )

        template_content = """
        {%
            from "common/macros/collections.html"
            import collection_question_with_add_another_summary_page with context
        %}
        {{ collection_question_with_add_another_summary_page(runner) }}
        """
        rendered_html = render_template_string(
            template_content,
            runner=FormRunner(SubmissionHelper.load(submission.id), question=question, is_clearing=True),
        )

        soup = BeautifulSoup(rendered_html, "html.parser")
        assert get_h1_text(soup) == "Remove your file"
        assert "Are you sure you want to remove your file?" in soup.get_text()
