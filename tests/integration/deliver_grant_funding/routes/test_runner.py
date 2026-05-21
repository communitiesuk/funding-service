from io import BytesIO

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.collections.types import FileUploadAnswer, IntegerAnswer, TextSingleLineAnswer, YesNoAnswer
from app.common.data.interfaces.collections import add_component_validation
from app.common.data.types import (
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    ExpressionType,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionModeEnum,
)
from app.common.expressions import ExpressionReference
from app.common.expressions.custom import CustomExpression
from tests.models import FactoryAnswer
from tests.utils import AnyStringMatching, get_h1_text, page_has_button


class TestSubmissionTasklist:
    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_submission_tasklist(self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(form__title="Colour information", form__collection__grant=grant)
        submission = factories.submission.create(collection=question.form.collection, created_by=client.user)

        response = client.get(
            url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=grant.id,
                submission_id=submission.id,
            )
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Colour information" in soup.text
            assert "Not started" in soup.text

    # todo: DGF submissions won't have grant recipients or be live for now
    @pytest.mark.parametrize(
        "client_fixture, submission_mode, expected_status_code",
        (
            ("authenticated_no_role_client", SubmissionModeEnum.PREVIEW, 403),
            ("authenticated_grant_member_client", SubmissionModeEnum.PREVIEW, 302),
            ("authenticated_grant_admin_client", SubmissionModeEnum.PREVIEW, 302),
        ),
    )
    def test_get_other_users_submission_tasklist_403s(
        self, request: FixtureRequest, client_fixture: str, factories, submission_mode, expected_status_code
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(form__title="Colour information", form__collection__grant=grant)

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(
            collection=question.form.collection, created_by=generic_user, mode=submission_mode
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=grant.id,
                submission_id=generic_submission.id,
            )
        )
        assert response.status_code == expected_status_code

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_submission_tasklist_test(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(form__title="Colour information", form__collection__grant=grant)
        submission = factories.submission.create(
            collection=question.form.collection,
            created_by=client.user,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("test answer"))],
        )
        factories.submission_event.create(
            created_by=client.user, submission=submission, related_entity_id=question.form.id
        )

        with client.session_transaction() as session:
            session["test_submission_form_id"] = question.form.id

        response = client.post(
            url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            ),
            data={"submit": True},
            follow_redirects=False,
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "deliver_grant_funding.return_from_test_submission",
                collection_id=question.form.collection.id,
                finished=1,
            )
            assert response.location == expected_location

    def test_post_submission_tasklist_shows_validation_error_when_answers_invalid(
        self, authenticated_grant_admin_client, factories
    ):
        client = authenticated_grant_admin_client
        grant = client.grant
        form = factories.form.create(title="Financial Report", collection__grant=grant)
        q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=0, name="threshold")
        q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1, name="amount")

        factories.expression.create(
            question=q2,
            created_by=client.user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.create(
            collection=form.collection,
            created_by=client.user,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=150)),
                FactoryAnswer(q2, IntegerAnswer(value=100)),
            ],
        )
        factories.submission_event.create(
            created_by=client.user,
            submission=submission,
            related_entity_id=form.id,
        )

        with client.session_transaction() as session:
            session["test_submission_form_id"] = form.id

        response = client.post(
            url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=form.id,
            ),
            data={"submit": True},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You cannot submit because you need to review some answers" in soup.text
        assert "amount" in soup.text


class TestAskAQuestion:
    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_ask_a_question(self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.collection, created_by=client.user)

        response = client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
            )
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "What's your favourite colour?" in soup.text

    @pytest.mark.parametrize(
        "show_on_same_page",
        (True, False),
    )
    def test_get_ask_a_question_with_add_another_context(
        self, show_on_same_page: bool, authenticated_grant_admin_client, factories
    ):
        group = factories.group.create(
            add_another=True,
            name="Your colour preferences",
            form__title="Colour information",
            form__collection__grant=authenticated_grant_admin_client.grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=show_on_same_page),
        )
        question = factories.question.create(
            text="What's your favourite colour?",
            parent=group,
            form=group.form,
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Blue"), add_another_index=0)],
        )
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                question_id=question.id,
                add_another_index=0,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What's your favourite colour?" in soup.text

        # appropriate add another context was used to display
        expected_caption = "Colour information" if show_on_same_page else "Your colour preferences (1)"
        assert expected_caption in soup.text

        expected_heading = "Your colour preferences (1)" if show_on_same_page else "What's your favourite colour?"
        assert get_h1_text(soup) == expected_heading

        # appropriate add another context was used for pre-populating
        assert soup.find("input", {"id": question.safe_qid}).get("value") == "Blue"

    def test_get_ask_a_question_add_another_condition_shows(self, authenticated_grant_admin_client, factories):
        group = factories.group.create(
            add_another=True,
            name="Your colour preferences",
            form__title="Colour information",
            form__collection__grant=authenticated_grant_admin_client.grant,
        )
        question = factories.question.create(
            text="Do you have a favourite colour?",
            data_type=QuestionDataType.YES_NO,
            parent=group,
            form=group.form,
        )
        question_2 = factories.question.create(
            text="What's your favourite colour?",
            parent=group,
            form=question.form,
        )
        factories.expression.create(
            question=question_2,
            created_by=authenticated_grant_admin_client.user,
            type_=ExpressionType.CONDITION,
            context={"subject_reference": ExpressionReference.from_question(question)},
            statement=f"{question.safe_qid} is True",
            managed_name=ManagedExpressionsEnum.IS_YES,
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[
                FactoryAnswer(question, YesNoAnswer(True), add_another_index=0),
                FactoryAnswer(question, YesNoAnswer(False), add_another_index=1),
            ],
        )

        # the first entry does meet the condition constraints and should be shown
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
                add_another_index=0,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What's your favourite colour?" in soup.text

        # the second entry doesn't meet the conditions constraints and should not be shown
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
                add_another_index=1,
            )
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.check_your_answers",
            grant_id=authenticated_grant_admin_client.grant.id,
            submission_id=submission.id,
            form_id=question.form.id,
        )

    # todo: DGF submissions won't have grant recipients or be live for now
    @pytest.mark.parametrize(
        "client_fixture, submission_mode, expected_status_code",
        (
            ("authenticated_no_role_client", SubmissionModeEnum.PREVIEW, 403),
            ("authenticated_grant_member_client", SubmissionModeEnum.PREVIEW, 302),
            ("authenticated_grant_admin_client", SubmissionModeEnum.PREVIEW, 302),
        ),
    )
    def test_get_other_users_ask_a_question_403s(
        self, request: FixtureRequest, client_fixture: str, factories, submission_mode, expected_status_code
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant,
        )

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(
            collection=question.form.collection, created_by=generic_user, mode=submission_mode
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=generic_submission.id,
                question_id=question.id,
            )
        )
        assert response.status_code == expected_status_code

    def test_get_ask_a_question_with_failing_condition_redirects(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        user = authenticated_grant_admin_client.user
        question = factories.question.create(form__collection__grant=grant)
        submission = factories.submission.create(collection=question.form.collection, created_by=user)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
            ),
        )
        assert response.status_code == 200

        # the question should no longer be accessible
        factories.expression.create(question=question, type_=ExpressionType.CONDITION, statement="False")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
            ),
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.check_your_answers",
            grant_id=grant.id,
            submission_id=submission.id,
            form_id=question.form.id,
        )

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_ask_a_question(self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            order=0,
            form__title="Colour information",
            form__collection__grant=grant,
        )
        question_2 = factories.question.create(
            text="What's your least favourite colour?",
            order=1,
            form=question.form,
        )
        submission = factories.submission.create(collection=question.form.collection, created_by=client.user)

        # Redirect to next question on successful post
        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
            ),
            data={"submit": True, question.safe_qid: "Blue"},
            follow_redirects=False,
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
            )
            assert response.location == expected_location

        # Redirect to check your answers on successful post
        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
            ),
            data={"submit": True, question_2.safe_qid: "Orange"},
            follow_redirects=False,
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            )
            assert response.location == expected_location

    def test_post_ask_a_question_add_another_context(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            add_another=True,
            form__collection__grant=grant,
        )
        question = factories.question.create(text="What's your favourite colour?", parent=group, form=group.form)
        question_2 = factories.question.create(
            text="What's your least favourite colour?",
            parent=group,
            form=group.form,
        )
        submission = factories.submission.create(
            collection=question.form.collection, created_by=authenticated_grant_admin_client.user
        )

        # Redirect to next question maintaining add another context on successful post
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
                add_another_index=0,
            ),
            data={"submit": True, question.safe_qid: "Blue"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=grant.id,
            submission_id=submission.id,
            question_id=question_2.id,
            add_another_index=0,
        )
        assert response.location == expected_location

        # Redirect to add another summary on successful post
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
                add_another_index=0,
            ),
            data={"submit": True, question_2.safe_qid: "Orange"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=grant.id,
            submission_id=submission.id,
            question_id=question_2.id,
        )
        assert response.location == expected_location

    def test_post_ask_a_question_skips_for_existing_file_upload_answer_add_another_context(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            add_another=True,
            form__collection__grant=grant,
        )
        question = factories.question.create(
            text="Upload a file",
            data_type=QuestionDataType.FILE_UPLOAD,
            parent=group,
            form=group.form,
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            created_by=authenticated_grant_admin_client.user,
            mode=SubmissionModeEnum.PREVIEW,
        )

        # response correctly checks non existing add another 0 index and requires the file
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
                add_another_index=0,
            ),
            data={"submit": "y", question.safe_qid: (BytesIO(b"file content"), "test.pdf")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=grant.id,
            submission_id=submission.id,
            question_id=question.id,
        )
        assert response.location == expected_location

        assert len(mock_s3_service_calls.upload_file_calls) == 1
        assert (
            mock_s3_service_calls.upload_file_calls[0].args[1]
            == f"uploaded-submission-files/preview/{submission.collection_id}/{submission.id}/{question.id}/0"
        )

        # response correctly checks the now persisted answer and allows skipping
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=question.id,
                add_another_index=0,
            ),
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=grant.id,
            submission_id=submission.id,
            question_id=question.id,
        )
        assert response.location == expected_location

        # no more files have been uploaded
        assert len(mock_s3_service_calls.upload_file_calls) == 1

    def test_post_ask_a_question_clears_file_upload_answer(
        self, authenticated_grant_recipient_data_provider_client, factories, mock_s3_service_calls
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        question = factories.question.create(
            text="Upload a file",
            data_type=QuestionDataType.FILE_UPLOAD,
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            answers=[
                FactoryAnswer(
                    question,
                    FileUploadAnswer(filename="test.pdf", size=0, mime_type="application/pdf", key="an-s3-key"),
                )
            ],
        )

        assert submission.data_manager.get(question) is not None

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
                action="clear",
            ),
            data={"confirm_remove": "yes"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "access_grant_funding.ask_a_question",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            question_id=question.id,
        )
        # we returned back to the same quesiton
        assert response.location == expected_location

        assert submission.data_manager.get(question) is None

        assert len(mock_s3_service_calls.delete_file_calls) == 1

    def test_question_without_guidance_uses_question_as_heading(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading=None,
            guidance_body=None,
            form__collection__grant=authenticated_grant_admin_client.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, created_by=authenticated_grant_admin_client.user
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == "What's your favourite colour?"

    def test_question_with_guidance_uses_guidance_heading(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading="Important instructions",
            guidance_body="Please read this carefully before answering",
            form__collection__grant=authenticated_grant_admin_client.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, created_by=authenticated_grant_admin_client.user
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == "Important instructions"
        assert "Please read this carefully before answering" in soup.text
        assert soup.select_one("label").text.strip() == "What's your favourite colour?"

    def test_group_same_page_with_questions_uses_group_guidance(self, authenticated_grant_admin_client, factories):
        group = factories.group.create(
            text="Group title - should not be used",
            guidance_heading="Group guidance heading",
            guidance_body="Group guidance body",
            form__collection__grant=authenticated_grant_admin_client.grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.create(
            parent=group,
            form=group.form,
            guidance_heading="Question guidance heading",
            guidance_body="Question guidance body",
        )
        q2 = factories.question.create(parent=group, form=group.form)
        submission = factories.submission.create(
            collection=group.form.collection, created_by=authenticated_grant_admin_client.user
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                question_id=q1.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == "Group guidance heading"
        assert "Group guidance body" in soup.text
        assert "Question guidance heading" not in soup.text
        assert "Question guidance body" not in soup.text
        assert [label.text.strip() for label in soup.select("label")] == [q1.text, q2.text]

    class TestAskAQuestionAddAnotherSummary:
        def test_get_add_another_summary_empty(self, authenticated_grant_admin_client, factories):
            group = factories.group.create(add_another=True, name="Test groups", text="Test groups")
            q1 = factories.question.create(form=group.form, parent=group)
            _ = factories.question.create(form=group.form, parent=group)
            submission = factories.submission.create(
                collection=group.form.collection, created_by=authenticated_grant_admin_client.user
            )

            response = authenticated_grant_admin_client.get(
                url_for(
                    "deliver_grant_funding.ask_a_question",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    submission_id=submission.id,
                    question_id=q1.id,
                )
            )

            # loading the question page for an add another question without an index loads the add another summary page
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Test groups"
            assert "You have not added any test groups." in soup.text
            assert "Add the first answer" in soup.text

            # because there's no data we should be configured to add the first answer but its not the users choice
            assert "govuk-!-display-none" in soup.find("div", {"class": "govuk-radios"}).get("class")
            assert soup.find("input", {"name": "add_another", "value": "yes"}).get("checked") is not None

        def test_get_ask_a_question_add_another_summary_with_data(self, authenticated_grant_admin_client, factories):
            group = factories.group.create(add_another=True, name="Test groups", text="Test groups")
            q1 = factories.question.create(form=group.form, parent=group)
            q2 = factories.question.create(form=group.form, parent=group)

            group.presentation_options = QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id])
            submission = factories.submission.create(
                collection=group.form.collection,
                created_by=authenticated_grant_admin_client.user,
                answers=[
                    FactoryAnswer(q1, TextSingleLineAnswer("E1A1"), add_another_index=0),
                    FactoryAnswer(q2, TextSingleLineAnswer("E2A2"), add_another_index=1),
                    FactoryAnswer(q1, TextSingleLineAnswer("E3A1"), add_another_index=2),
                    FactoryAnswer(q2, TextSingleLineAnswer("E3A2"), add_another_index=2),
                    FactoryAnswer(q1, TextSingleLineAnswer("E4A1"), add_another_index=3),
                    FactoryAnswer(q2, TextSingleLineAnswer("E4A2"), add_another_index=3),
                ],
            )

            response = authenticated_grant_admin_client.get(
                url_for(
                    "deliver_grant_funding.ask_a_question",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    submission_id=submission.id,
                    question_id=q1.id,
                )
            )

            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Test groups"
            assert "You have added 4 test groups" in soup.text

            # partial entries have a link as the main call to action like similar to CYA (summary shown if available)
            assert (
                soup.find_all("dt", {"class": "govuk-summary-list__key"})[0].text.strip()
                == "Enter missing information for first test groups (E1A1)"
            )

            # summary not shown if not available
            assert (
                soup.find_all("dt", {"class": "govuk-summary-list__key"})[1].text.strip()
                == "Enter missing information for second test groups"
            )

            # each entry in the row respects the summary line configuration even if more answers are available
            assert soup.find_all("dt", {"class": "govuk-summary-list__key"})[2].text.strip() == "E3A1"

            # do you want to add another component is shown and defaults to nothing selected
            assert "govuk-!-display-none" not in soup.find("div", {"class": "govuk-radios"}).get("class")
            assert soup.find("input", {"name": "add_another", "value": "yes"}).get("checked") is None
            assert soup.find("input", {"name": "add_another", "value": "no"}).get("checked") is None

        def test_post_add_first_answer_redirects_to_index_0(self, authenticated_grant_admin_client, factories):
            group = factories.group.create(add_another=True, name="Test groups", text="Test groups")
            q1 = factories.question.create(form=group.form, parent=group)
            submission = factories.submission.create(
                collection=group.form.collection, created_by=authenticated_grant_admin_client.user
            )

            response = authenticated_grant_admin_client.post(
                url_for(
                    "deliver_grant_funding.ask_a_question",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    submission_id=submission.id,
                    question_id=q1.id,
                ),
                data={"add_another": "yes"},
            )

            assert response.status_code == 302
            assert response.location.endswith(f"/{q1.id}/0")


class TestGroupValidation:
    @staticmethod
    def _make_same_page_group_with_two_numbers(factories, grant, names=("capital", "revenue")):
        group = factories.group.create(
            name="Spend totals",
            text="Spend totals",
            form__title="Forecast spending",
            form__collection__grant=grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        capital = factories.question.create(
            name=names[0],
            text=f"Forecast spend on {names[0]}",
            data_type=QuestionDataType.NUMBER,
            order=0,
            parent=group,
            form=group.form,
        )
        revenue = factories.question.create(
            name=names[1],
            text=f"Forecast spend on {names[1]}",
            data_type=QuestionDataType.NUMBER,
            order=1,
            parent=group,
            form=group.form,
        )
        return group, capital, revenue

    def test_post_same_page_group_passing_validation_redirects(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        client = authenticated_grant_admin_client
        group, capital, revenue = self._make_same_page_group_with_two_numbers(factories, client.grant)
        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=f"(({capital.safe_qid})) + (({revenue.safe_qid})) == 1000",
                custom_message="Capital plus revenue must equal 1000",
            ),
        )
        submission = factories.submission.create(collection=group.form.collection, created_by=client.user)

        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=client.grant.id,
                submission_id=submission.id,
                question_id=capital.id,
            ),
            data={"submit": True, capital.safe_qid: "400", revenue.safe_qid: "600"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(r".*/check-yours-answers/.*"), (
            "Should redirect to CYA page on success"
        )

        db_session.refresh(submission)
        assert submission.data_manager.get(capital) == IntegerAnswer(value=400)
        assert submission.data_manager.get(revenue) == IntegerAnswer(value=600)

    def test_post_same_page_group_failing_validation_shows_on_page_summary(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        client = authenticated_grant_admin_client
        group, capital, revenue = self._make_same_page_group_with_two_numbers(factories, client.grant)
        organisation = factories.organisation.create()
        grant_recipient = factories.grant_recipient.create(grant=client.grant, organisation=organisation)

        data_source = factories.data_source.create(
            name="Allocations",
            grant=client.grant,
            collection=group.form.collection,
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(prefix="£"),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Capital Allocation",
                    )
                }
            ),
        )
        factories.data_source_organisation_item.create(
            data_source=data_source,
            external_id=organisation.external_id,
            _data={"c_allocation": 1000},
        )

        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=(
                    f"(({capital.safe_qid})) + (({revenue.safe_qid})) == (({data_source.safe_did}.c_allocation))"
                ),
                custom_message="Capital plus revenue must equal 1000",
            ),
        )
        submission = factories.submission.create(
            collection=group.form.collection, created_by=client.user, grant_recipient=grant_recipient
        )

        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=client.grant.id,
                submission_id=submission.id,
                question_id=capital.id,
            ),
            data={"submit": True, capital.safe_qid: "400", revenue.safe_qid: "500"},
            follow_redirects=False,
        )

        assert response.status_code == 200, "Should return 200 and reload page on failure"
        assert response.location is None

        soup = BeautifulSoup(response.data, "html.parser")
        error_summary = soup.find("div", {"class": "govuk-error-summary"})
        assert error_summary is not None
        assert "Capital plus revenue must equal 1000" in error_summary.text
        assert "On this page:" in error_summary.text
        assert "On a different page:" not in error_summary.text
        assert "Other information referenced:" in error_summary.text
        assert "Capital Allocation" in error_summary.text
        assert "£1,000" in error_summary.text

        on_page_links = error_summary.find_all("a")
        on_page_link_texts = [a.text.strip() for a in on_page_links]
        assert any("capital" in t and "400" in t for t in on_page_link_texts)
        assert any("revenue" in t and "500" in t for t in on_page_link_texts)
        for link in on_page_links:
            assert link.get("href", "").startswith("#")

        for question in (capital, revenue):
            field = soup.find("input", {"id": question.safe_qid})
            assert field is not None
            assert "govuk-input--error" in (field.get("class") or [])

        db_session.refresh(submission)
        assert submission.data_manager.get(capital) is None
        assert submission.data_manager.get(revenue) is None

    def test_post_same_page_group_failing_validation_with_off_page_reference(
        self, authenticated_grant_admin_client, factories
    ):
        client = authenticated_grant_admin_client
        form = factories.form.create(title="Forecast spending", collection__grant=client.grant)
        total = factories.question.create(
            name="quarter_total",
            text="Forecast spend April to June 2026",
            data_type=QuestionDataType.NUMBER,
            order=0,
            form=form,
        )
        group = factories.group.create(
            name="Spend totals",
            text="Spend totals",
            form=form,
            order=1,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        capital = factories.question.create(
            name="capital",
            text="Forecast spend on capital",
            data_type=QuestionDataType.NUMBER,
            order=0,
            parent=group,
            form=form,
        )
        revenue = factories.question.create(
            name="revenue",
            text="Forecast spend on revenue",
            data_type=QuestionDataType.NUMBER,
            order=1,
            parent=group,
            form=form,
        )
        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=f"(({capital.safe_qid})) + (({revenue.safe_qid})) == (({total.safe_qid}))",
                custom_message="Capital plus revenue must equal the quarter total",
            ),
        )

        submission = factories.submission.create(
            collection=form.collection,
            created_by=client.user,
            answers=[FactoryAnswer(total, IntegerAnswer(value=1500))],
        )

        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=client.grant.id,
                submission_id=submission.id,
                question_id=capital.id,
            ),
            data={"submit": True, capital.safe_qid: "400", revenue.safe_qid: "500"},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        error_summary = soup.find("div", {"class": "govuk-error-summary"})
        assert error_summary is not None
        assert "Capital plus revenue must equal the quarter total" in error_summary.text
        assert "On this page:" in error_summary.text
        assert "On a different page:" in error_summary.text

        expected_off_page_url = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=client.grant.id,
            submission_id=submission.id,
            question_id=total.id,
        )
        off_page_links = [a for a in error_summary.find_all("a") if a.get("href") and not a.get("href").startswith("#")]
        assert any(link.get("href") == expected_off_page_url for link in off_page_links)
        assert any("quarter_total" in link.text and "1,500" in link.text for link in off_page_links)

    def test_post_same_page_group_stops_at_first_failed_group_validation(
        self, authenticated_grant_admin_client, factories
    ):
        client = authenticated_grant_admin_client
        group, capital, revenue = self._make_same_page_group_with_two_numbers(factories, client.grant)
        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=f"(({capital.safe_qid})) + (({revenue.safe_qid})) == 1000",
                custom_message="Rule A: capital plus revenue must equal 1000",
            ),
        )
        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=f"(({capital.safe_qid})) > 0",
                custom_message="Rule B: capital must be positive",
            ),
        )
        submission = factories.submission.create(collection=group.form.collection, created_by=client.user)

        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=client.grant.id,
                submission_id=submission.id,
                question_id=capital.id,
            ),
            data={"submit": True, capital.safe_qid: "100", revenue.safe_qid: "100"},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Rule A: capital plus revenue must equal 1000" in soup.text
        assert "Rule B: capital must be positive" not in soup.text

    def test_post_same_page_group_individual_validation_failure_short_circuits_group(
        self, authenticated_grant_admin_client, factories
    ):
        client = authenticated_grant_admin_client
        group, capital, revenue = self._make_same_page_group_with_two_numbers(factories, client.grant)
        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=f"(({capital.safe_qid})) + (({revenue.safe_qid})) == 1000",
                custom_message="Group rule should not appear",
            ),
        )
        submission = factories.submission.create(collection=group.form.collection, created_by=client.user)

        response = client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=client.grant.id,
                submission_id=submission.id,
                question_id=capital.id,
            ),
            data={"submit": True, capital.safe_qid: "", revenue.safe_qid: "500"},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Enter the capital" in soup.text
        assert "Group rule should not appear" not in soup.text

    def test_post_submission_tasklist_blocks_when_group_validation_fails(
        self, authenticated_grant_admin_client, factories
    ):
        client = authenticated_grant_admin_client
        group, capital, revenue = self._make_same_page_group_with_two_numbers(factories, client.grant)
        add_component_validation(
            group,
            client.user,
            CustomExpression(
                custom_expression=f"(({capital.safe_qid})) + (({revenue.safe_qid})) == 1000",
                custom_message="Capital plus revenue must equal 1000",
            ),
        )
        submission = factories.submission.create(
            collection=group.form.collection,
            created_by=client.user,
            answers=[
                FactoryAnswer(capital, IntegerAnswer(value=200)),
                FactoryAnswer(revenue, IntegerAnswer(value=300)),
            ],
        )
        factories.submission_event.create(
            created_by=client.user,
            submission=submission,
            related_entity_id=group.form.id,
        )

        with client.session_transaction() as session:
            session["test_submission_form_id"] = group.form.id

        response = client.post(
            url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=client.grant.id,
                submission_id=submission.id,
                form_id=group.form.id,
            ),
            data={"submit": True},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You cannot submit because you need to review some answers" in soup.text
        assert "Capital plus revenue must equal 1000" in soup.text


class TestCheckYourAnswers:
    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_check_your_answers(self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant,
        )

        submission = factories.submission.create(collection=question.form.collection, created_by=client.user)

        response = client.get(
            url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            )
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Check your answers" in soup.text
            assert "What's your favourite colour?" in soup.text
            assert "Colour information" in soup.text

    def test_get_check_your_answers_with_extracts_add_another(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=authenticated_grant_admin_client.grant,
        )
        group = factories.group.create(
            name="Favourite colour details",
            form=question.form,
            add_another=True,
        )
        nested_question_1 = factories.question.create(
            text="Why do you like this colour?", parent=group, form=group.form
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[
                FactoryAnswer(nested_question_1, TextSingleLineAnswer("First reason"), add_another_index=0),
                FactoryAnswer(nested_question_1, TextSingleLineAnswer("Second reason"), add_another_index=1),
            ],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Check your answers" in soup.text
        assert "Answers for “Favourite colour details”" in soup.text
        assert soup.find_all("h2", {"class": "govuk-summary-card__title"})[0].text.strip() == "First reason"
        assert soup.find_all("h2", {"class": "govuk-summary-card__title"})[1].text.strip() == "Second reason"
        assert (
            len(
                [
                    entry
                    for entry in soup.find_all("dt", {"class": "govuk-summary-list__key"})
                    if entry.text.strip() == "Why do you like this colour?"
                ]
            )
            == 2
        )

    # todo: DGF submissions won't have grant recipients or be live for now
    @pytest.mark.parametrize(
        "client_fixture, submission_mode, expected_status_code",
        (
            ("authenticated_no_role_client", SubmissionModeEnum.PREVIEW, 403),
            ("authenticated_grant_member_client", SubmissionModeEnum.PREVIEW, 302),
            ("authenticated_grant_admin_client", SubmissionModeEnum.PREVIEW, 302),
        ),
    )
    def test_get_other_users_check_your_answers_403s(
        self, request: FixtureRequest, client_fixture: str, factories, submission_mode, expected_status_code
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant,
        )

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(
            collection=question.form.collection, created_by=generic_user, mode=submission_mode
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=grant.id,
                submission_id=generic_submission.id,
                form_id=question.form.id,
            )
        )
        assert response.status_code == expected_status_code

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_check_your_answers_complete_form(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.collection, created_by=client.user)

        response = client.post(
            url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            ),
            follow_redirects=False,
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            )
            assert response.location == expected_location

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_check_your_answers_complete_test_preview(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.collection, created_by=client.user)

        with client.session_transaction() as session:
            session["test_submission_form_id"] = question.form.id

        response = client.post(
            url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=grant.id,
                submission_id=submission.id,
                form_id=question.form.id,
            ),
            follow_redirects=False,
        )
        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "deliver_grant_funding.return_from_test_submission",
                collection_id=question.form.collection.id,
                finished=1,
            )
            assert response.location == expected_location


class TestRemoveAddAnotherEntry:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_remove_add_another_entry(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant
        )
        q1 = factories.question.create(form=group.form, parent=group, name="Question 1")
        q2 = factories.question.create(form=group.form, parent=group, name="Question 2")
        group.presentation_options = QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id])
        submission = factories.submission.create(
            collection=group.form.collection,
            created_by=client.user,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 1"), add_another_index=0),
                FactoryAnswer(q2, TextSingleLineAnswer("Details 1"), add_another_index=0),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 2"), add_another_index=1),
                FactoryAnswer(q2, TextSingleLineAnswer("Details 2"), add_another_index=1),
            ],
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=0,
                action="remove",
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Are you sure you want to remove Entry 1?"
            assert page_has_button(soup, "Save and continue")

            radios = soup.find_all("input", {"type": "radio", "name": "confirm_remove"})
            assert len(radios) == 2

    def test_post_remove_add_another_entry_confirms_yes(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant
        )
        q1 = factories.question.create(form=group.form, parent=group)
        q2 = factories.question.create(form=group.form, parent=group)
        submission = factories.submission.create(
            collection=group.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 1"), add_another_index=0),
                FactoryAnswer(q2, TextSingleLineAnswer("Details 1"), add_another_index=0),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 2"), add_another_index=1),
                FactoryAnswer(q2, TextSingleLineAnswer("Details 2"), add_another_index=1),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 3"), add_another_index=2),
                FactoryAnswer(q2, TextSingleLineAnswer("Details 3"), add_another_index=2),
            ],
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=1,
                action="remove",
            ),
            data={"confirm_remove": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        expected_location = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=grant.id,
            submission_id=submission.id,
            question_id=q1.id,
        )
        assert response.location == expected_location

        assert submission.data_manager.get_count_for_add_another(group) == 2
        assert submission.data_manager.get(q1, add_another_index=1) == TextSingleLineAnswer("Entry 3")

    def test_post_remove_add_another_entry_confirms_no(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant
        )
        q1 = factories.question.create(form=group.form, parent=group)
        submission = factories.submission.create(
            collection=group.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 1"), add_another_index=0),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 2"), add_another_index=1),
            ],
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=0,
                action="remove",
            ),
            data={"confirm_remove": "no"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        expected_location = url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=grant.id,
            submission_id=submission.id,
            question_id=q1.id,
        )
        assert response.location == expected_location

        assert submission.data_manager.get_count_for_add_another(group) == 2
        assert submission.data_manager.get(q1, add_another_index=0) == TextSingleLineAnswer("Entry 1")

    def test_post_remove_add_another_entry_with_matching_check_entries(
        self, authenticated_grant_admin_client, factories
    ):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant
        )
        q1 = factories.question.create(form=group.form, parent=group)
        submission = factories.submission.create(
            collection=group.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 1"), add_another_index=0),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 2"), add_another_index=1),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 3"), add_another_index=2),
            ],
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=0,
                action="remove",
                check_entries=3,
            ),
            data={"confirm_remove": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert submission.data_manager.get_count_for_add_another(group) == 2
        assert submission.data_manager.get(q1, add_another_index=0) == TextSingleLineAnswer("Entry 2")

    def test_post_remove_add_another_entry_with_mismatched_check_entries_redirects(
        self, authenticated_grant_admin_client, factories
    ):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant
        )
        q1 = factories.question.create(form=group.form, parent=group)
        submission = factories.submission.create(
            collection=group.form.collection,
            created_by=authenticated_grant_admin_client.user,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 1"), add_another_index=0),
                FactoryAnswer(q1, TextSingleLineAnswer("Entry 2"), add_another_index=1),
            ],
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=0,
                action="remove",
                check_entries=3,
            ),
            data={"confirm_remove": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        # no entries are removed
        assert submission.data_manager.get_count_for_add_another(group) == 2
