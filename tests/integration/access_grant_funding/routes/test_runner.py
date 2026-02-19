from datetime import date, datetime

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Submission
from app.common.data.types import (
    ExpressionType,
    ManagedExpressionsEnum,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.helpers.collections import SubmissionHelper
from tests.utils import AnyStringMatching, get_h1_text, page_has_button, page_has_error, page_has_h2, page_has_link


class TestRouteToSubmission:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_route_to_submission_access(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        submission = factories.submission.create(
            grant_recipient=grant_recipient, collection__grant=grant_recipient.grant, mode=SubmissionModeEnum.LIVE
        )

        response = client.get(
            url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=submission.collection.id,
            ),
            follow_redirects=False,
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = (
                f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
                f"/reports/{submission.id}/tasklist"
            )
            assert response.location == expected_location

    def test_route_to_submission_creates_submission_if_missing(
        self, db_session, factories, authenticated_grant_recipient_member_client
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        collection = factories.collection.create(grant=grant_recipient.grant)

        submissions = db_session.query(Submission).where(Submission.grant_recipient_id == grant_recipient.id).all()
        assert len(submissions) == 0

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302

        submissions = db_session.query(Submission).where(Submission.grant_recipient_id == grant_recipient.id).all()
        assert len(submissions) == 1
        assert str(submissions[0].id) in response.location

    def test_route_to_submission_redirects_to_submissions_list_when_multiple_submissions_enabled(
        self, factories, authenticated_grant_recipient_member_client
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        collection = factories.collection.create(grant=grant_recipient.grant, allow_multiple_submissions=True)

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collection_submissions",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            collection_id=collection.id,
        )

    def test_route_to_submission_redirects_to_locked_page_if_locked(
        self, factories, authenticated_grant_recipient_member_client, submission_awaiting_sign_off
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=submission_awaiting_sign_off.collection.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302
        expected_location = (
            f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
            f"/reports/{submission_awaiting_sign_off.id}/view"
        )
        assert response.location == expected_location


class TestTasklist:
    @pytest.mark.parametrize(
        "client_fixture, can_access, can_edit, requires_certification",
        (
            ("authenticated_no_role_client", False, False, True),
            ("authenticated_grant_recipient_member_client", True, False, True),
            ("authenticated_grant_recipient_data_provider_client", True, True, True),
            ("authenticated_grant_recipient_data_provider_client", True, True, False),
        ),
    )
    def test_get_tasklist(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
        can_edit: bool,
        factories,
        requires_certification,
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
            form__collection__requires_certification=requires_certification,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = client.get(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Colour information" in soup.text
            assert "Not started" in soup.text

            if requires_certification:
                submission_heading = page_has_h2(soup, "Submit your report to your certifier")
                submission_action = page_has_button(soup, "Submit report to certifier")
            else:
                submission_heading = page_has_h2(soup, "Submit your report")
                submission_action = page_has_button(soup, "Continue to submit")
            tasklist_action = page_has_link(soup, "Colour information")

            if can_edit:
                assert submission_heading is not None
                assert submission_action is not None

                # an empty form links to the first question
                assert tasklist_action["href"] == (
                    f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
                    f"/reports/{submission.id}/questions/{question.id}"
                )
            else:
                assert submission_heading is None
                assert submission_action is None

                # even empty forms don't go to question if you can't edit
                assert tasklist_action["href"] == (
                    f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
                    f"/reports/{submission.id}/check-your-answers/{question.form.id}?source=tasklist"
                )

    @pytest.mark.parametrize(
        "submission_fixture",
        (
            "submission_awaiting_sign_off",
            "submission_submitted",
        ),
    )
    def test_get_tasklist_redirects_if_report_is_locked(
        self,
        authenticated_grant_recipient_data_provider_client,
        request: FixtureRequest,
        submission_fixture: str,
    ):
        submission = request.getfixturevalue(submission_fixture)
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302
        expected_location = url_for(
            "access_grant_funding.view_locked_report",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
        )
        assert response.location == expected_location

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", True),
        ),
    )
    @pytest.mark.freeze_time("2025-01-02 12:00:00")
    def test_post_tasklist_complete_submission_send_for_sign_off(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, mock_notification_service_calls
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            form__title="Colour information", form__collection__grant=grant_recipient.grant
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): "Blue"},
        )
        factories.submission_event.create(
            created_by=client.user,
            submission=submission,
            related_entity_id=question.form.id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            created_at_utc=datetime(2025, 1, 1, 12, 0, 0),
        )

        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            permissions=[RoleEnum.CERTIFIER],
        )

        response = client.post(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            ),
            data={"submit": "y"},
            follow_redirects=False,
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302

            expected_location = (
                f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
                f"/reports/{submission.id}/sent-for-sign-off-confirmation"
            )
            assert response.location == expected_location

            # 1 email for the data provider, 1 email for the certifier
            assert len(mock_notification_service_calls) == 2
            data_provider_confirmation_email = mock_notification_service_calls[0]
            certifier_notification_email = mock_notification_service_calls[1]
            assert data_provider_confirmation_email.kwargs["personalisation"]["grant_report_url"] == AnyStringMatching(
                r"http://funding.communities.gov.localhost:8080/access/organisation/.+/grants/.+/reports/.+"
            )
            assert certifier_notification_email.kwargs["personalisation"]["report_submitter"] == client.user.name

    @pytest.mark.freeze_time("2025-01-02 12:00:00")
    def test_post_tasklist_complete_submission_no_certification_redirects(
        self,
        authenticated_grant_recipient_data_provider_client,
        grant_recipient,
        submission_ready_to_submit,
    ):
        helper = SubmissionHelper(submission_ready_to_submit)
        assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
        submission_ready_to_submit.collection.requires_certification = False
        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_ready_to_submit.id,
            ),
            data={"submit": "y"},
            follow_redirects=False,
        )

        expected_location = (
            f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
            f"/reports/{submission_ready_to_submit.id}/confirm-report-submission"
        )
        assert response.location == expected_location
        assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

    @pytest.mark.freeze_time("2025-01-02 12:00:00")
    def test_post_tasklist_complete_submission_sends_for_certification(
        self,
        authenticated_grant_recipient_data_provider_client,
        grant_recipient,
        mock_notification_service_calls,
        submission_ready_to_submit,
        data_provider_user,
    ):
        helper = SubmissionHelper(submission_ready_to_submit)
        assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT
        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_ready_to_submit.id,
            ),
            data={"submit": "y"},
            follow_redirects=False,
        )

        expected_location = (
            f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
            f"/reports/{submission_ready_to_submit.id}/sent-for-sign-off-confirmation"
        )
        assert response.location == expected_location
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        # 1 email for the data provider, plus generic user that exists for the client
        assert len(mock_notification_service_calls) == 2
        data_provider_confirmation_email = mock_notification_service_calls[0]
        assert data_provider_confirmation_email.kwargs["personalisation"]["grant_report_url"] == AnyStringMatching(
            r"http://funding.communities.gov.localhost:8080/access/organisation/.+/grants/.+/reports/.+"
        )

    def test_post_tasklist_shows_validation_error_when_answers_invalid(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        grant_recipient = client.grant_recipient
        form = factories.form.create(title="Financial Report", collection__grant=grant_recipient.grant)
        q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=0, name="threshold")
        q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1, name="amount")

        factories.expression.create(
            question=q2,
            created_by=client.user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={"question_id": str(q2.id), "minimum_value": None, "minimum_expression": f"(({q1.safe_qid}))"},
        )

        submission = factories.submission.create(
            collection=form.collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(q1.id): {"value": 150}, str(q2.id): {"value": 100}},
        )
        factories.submission_event.create(
            created_by=client.user,
            submission=submission,
            related_entity_id=form.id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )

        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            permissions=[RoleEnum.CERTIFIER],
        )

        response = client.post(
            url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            ),
            data={"submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You cannot submit because you need to review some answers" in soup.text
        assert "amount" in soup.text


class TestAskAQuestion:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", True),
        ),
    )
    def test_get_ask_a_question(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            )
        )
        if not can_access:
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
        self, show_on_same_page: bool, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            add_another=True,
            name="Your colour preferences",
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=show_on_same_page),
        )
        question = factories.question.create(
            text="What's your favourite colour?",
            parent=group,
            form=group.form,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )
        submission.data = {str(group.id): [{str(question.id): "Blue"}]}
        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
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

    def test_get_ask_a_question_add_another_condition_shows(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            add_another=True,
            name="Your colour preferences",
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
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
            created_by=authenticated_grant_recipient_data_provider_client.user,
            type_=ExpressionType.CONDITION,
            context={"question_id": str(question.id)},
            statement=f"{question.safe_qid} is True",
            managed_name=ManagedExpressionsEnum.IS_YES,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )
        submission.data = {str(group.id): [{str(question.id): True}, {str(question.id): False}]}

        # the first entry does meet the condition constraints and should be shown
        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
                add_another_index=0,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What's your favourite colour?" in soup.text

        # the second entry doesn't meet the conditions constraints and should not be shown
        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
                add_another_index=1,
            )
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.check_your_answers",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            section_id=question.form.id,
        )

    def test_get_ask_a_question_with_failing_condition_redirects(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        question = factories.question.create(form__collection__grant=grant_recipient.grant)
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            ),
        )
        assert response.status_code == 200

        # the question should no longer be accessible
        factories.expression.create(question=question, type_=ExpressionType.CONDITION, statement="False")

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            ),
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.check_your_answers",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            section_id=question.form.id,
        )

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", True),
        ),
    )
    def test_post_ask_a_question(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            order=0,
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
        )
        question_2 = factories.question.create(
            text="What's your least favourite colour?",
            order=1,
            form=question.form,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        # Redirect to next question on successful post
        response = client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            ),
            data={"submit": "y", question.safe_qid: "Blue"},
            follow_redirects=False,
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
            )
            assert response.location == expected_location

        # Redirect to check your answers on successful post
        response = client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
            ),
            data={"submit": "y", question_2.safe_qid: "Orange"},
            follow_redirects=False,
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "access_grant_funding.check_your_answers",
                grant_id=grant_recipient.grant.id,
                organisation_id=grant_recipient.organisation.id,
                submission_id=submission.id,
                section_id=question.form.id,
            )
            assert response.location == expected_location

    @pytest.mark.parametrize(
        "data_to_submit_for_number_question, expected_error_message",
        [
            (None, "Enter the number question"),
            ("", "Enter the number question"),
            ("words", "The answer must be a whole number, like 100"),
        ],
    )
    def test_post_ask_a_question_generates_back_link_correctly_with_invalid_user_input(
        self,
        authenticated_grant_recipient_data_provider_client,
        factories,
        data_to_submit_for_number_question,
        expected_error_message,
    ):
        # This test exists to prevent regression of a bug where the evaluation context was polluted by validation,
        # and this scenario in this test resulted in an exception:
        # TypeError: '<' not supported between instances of 'NoneType' and 'int'
        grant_recipient = (
            getattr(authenticated_grant_recipient_data_provider_client, "grant_recipient", None)
            or factories.grant_recipient.create()
        )
        form = factories.form.create(title="number form", collection__grant=grant_recipient.grant)
        question_1 = factories.question.create(
            text="Enter a number",
            data_type=QuestionDataType.NUMBER,
            name="number question",
            order=0,
            form=form,
        )
        question_2 = factories.question.create(
            text="Why so low?",
            order=1,
            form=form,
        )
        factories.question.create(
            text="Another question",
            order=2,
            form=form,
        )
        factories.expression.create(
            question=question_2,
            created_by=authenticated_grant_recipient_data_provider_client.user,
            type_=ExpressionType.CONDITION,
            statement=f"{question_1.safe_qid} < 5",
            managed_name=ManagedExpressionsEnum.LESS_THAN,
            context={"question_id": str(question_2.id), "maximum_value": 5},
        )
        submission = factories.submission.create(
            collection=form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_1.id,
            ),
            data={"submit": "y", question_1.safe_qid: data_to_submit_for_number_question},
            follow_redirects=False,
        )
        # expect a 200 - same page, but with the error message
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, expected_error_message)

    def test_post_ask_a_question_generates_next_url_with_latest_data_after_saving_question(
        self,
        authenticated_grant_recipient_data_provider_client,
        factories,
    ):
        grant_recipient = (
            getattr(authenticated_grant_recipient_data_provider_client, "grant_recipient", None)
            or factories.grant_recipient.create()
        )
        form = factories.form.create(title="number form", collection__grant=grant_recipient.grant)
        question_1 = factories.question.create(
            text="Enter a number",
            data_type=QuestionDataType.NUMBER,
            name="number question",
            order=0,
            form=form,
        )
        question_2 = factories.question.create(
            text="Why so low?",
            order=1,
            form=form,
        )
        factories.question.create(
            text="Another question",
            order=2,
            form=form,
        )
        factories.expression.create(
            question=question_2,
            created_by=authenticated_grant_recipient_data_provider_client.user,
            type_=ExpressionType.CONDITION,
            statement=f"{question_1.safe_qid} < 5",
            managed_name=ManagedExpressionsEnum.LESS_THAN,
            context={"question_id": str(question_2.id), "maximum_value": 5},
        )
        submission = factories.submission.create(
            collection=form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_1.id,
            ),
            data={"submit": "y", question_1.safe_qid: 3},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "access_grant_funding.ask_a_question",
            grant_id=grant_recipient.grant.id,
            organisation_id=grant_recipient.organisation.id,
            submission_id=submission.id,
            question_id=question_2.id,
        )
        assert response.location == expected_location

    def test_post_ask_a_question_add_another_context(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            add_another=True,
            form__collection__grant=grant_recipient.grant,
        )
        question = factories.question.create(text="What's your favourite colour?", parent=group, form=group.form)
        question_2 = factories.question.create(
            text="What's your least favourite colour?",
            parent=group,
            form=group.form,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        # Redirect to next question maintaining add another context on successful post
        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
                add_another_index=0,
            ),
            data={"submit": "y", question.safe_qid: "Blue"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "access_grant_funding.ask_a_question",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            question_id=question_2.id,
            add_another_index=0,
        )
        assert response.location == expected_location

        # Redirect to add another summary on successful post
        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question_2.id,
                add_another_index=0,
            ),
            data={"submit": "y", question_2.safe_qid: "Orange"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        expected_location = url_for(
            "access_grant_funding.ask_a_question",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            question_id=question_2.id,
        )
        assert response.location == expected_location

    def test_question_without_guidance_uses_question_as_heading(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading=None,
            guidance_body=None,
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == "What's your favourite colour?"

    def test_question_with_guidance_uses_guidance_heading(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading="Important instructions",
            guidance_body="Please read this carefully before answering",
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == "Important instructions"
        assert "Please read this carefully before answering" in soup.text
        assert soup.select_one("label").text.strip() == "What's your favourite colour?"

    def test_group_same_page_with_questions_uses_group_guidance(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            text="Group title - should not be used",
            guidance_heading="Group guidance heading",
            guidance_body="Group guidance body",
            form__collection__grant=grant_recipient.grant,
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
            collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
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
        def test_get_add_another_summary_empty(self, authenticated_grant_recipient_data_provider_client, factories):
            grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
            group = factories.group.create(
                add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
            )
            q1 = factories.question.create(form=group.form, parent=group)
            _ = factories.question.create(form=group.form, parent=group)
            submission = factories.submission.create(
                collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
            )

            response = authenticated_grant_recipient_data_provider_client.get(
                url_for(
                    "access_grant_funding.ask_a_question",
                    organisation_id=grant_recipient.organisation.id,
                    grant_id=grant_recipient.grant.id,
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

        def test_get_ask_a_question_add_another_summary_with_data(
            self, authenticated_grant_recipient_data_provider_client, factories
        ):
            grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
            group = factories.group.create(
                add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
            )
            q1 = factories.question.create(form=group.form, parent=group)
            q2 = factories.question.create(form=group.form, parent=group)

            submission = factories.submission.create(
                collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
            )

            group.presentation_options = QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id])
            submission.data = {
                str(group.id): [
                    {str(q1.id): "E1A1"},
                    {str(q2.id): "E2A2"},
                    {str(q1.id): "E3A1", str(q2.id): "E3A2"},
                    {str(q1.id): "E4A1", str(q2.id): "E4A2"},
                ]
            }

            response = authenticated_grant_recipient_data_provider_client.get(
                url_for(
                    "access_grant_funding.ask_a_question",
                    organisation_id=grant_recipient.organisation.id,
                    grant_id=grant_recipient.grant.id,
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

            # All rows have remove links
            rows = soup.find_all("div", {"class": "govuk-summary-list__row"})

            # first data entries are incomplete so have no change but have remove
            assert page_has_link(rows[0], "Remove") is not None
            assert page_has_link(rows[0], "Change") is None
            assert page_has_link(rows[1], "Remove") is not None
            assert page_has_link(rows[1], "Change") is None

            # subsequent data entires are complete and have both change and remove
            assert page_has_link(rows[2], "Remove") is not None
            assert page_has_link(rows[2], "Change") is not None
            assert page_has_link(rows[3], "Remove") is not None
            assert page_has_link(rows[3], "Change") is not None

            # do you want to add another component is shown and defaults to nothing selected
            assert "govuk-!-display-none" not in soup.find("div", {"class": "govuk-radios"}).get("class")
            assert soup.find("input", {"name": "add_another", "value": "yes"}).get("checked") is None
            assert soup.find("input", {"name": "add_another", "value": "no"}).get("checked") is None


class TestCheckYourAnswers:
    @pytest.mark.parametrize(
        "client_fixture, can_access, can_edit",
        (
            ("authenticated_no_role_client", False, False),
            ("authenticated_grant_recipient_member_client", True, False),
            ("authenticated_grant_recipient_data_provider_client", True, True),
        ),
    )
    def test_get_check_your_answers(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, can_edit: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            name="favourite colour",
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
        )

        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = client.get(
            url_for(
                "access_grant_funding.check_your_answers",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                section_id=question.form.id,
            )
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Check your answers" in soup.text
            assert "What's your favourite colour?" in soup.text
            assert "Colour information" in soup.text

            continue_button = page_has_button(soup, "Save and continue")
            return_to_tasklist_link = page_has_link(soup, "Return to the task list")
            edit_action_link = page_has_link(soup, "Enter favourite colour")

            if can_edit:
                assert continue_button is not None
                assert edit_action_link is not None
                assert return_to_tasklist_link is None
            else:
                assert continue_button is None
                assert edit_action_link is None
                assert return_to_tasklist_link is not None
                assert soup.find("dd", {"class": "govuk-summary-list__value"}).text.strip() == "(Not answered)"

        submission.data = {str(question.id): "Blue"}

        response = client.get(
            url_for(
                "access_grant_funding.check_your_answers",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                section_id=question.form.id,
            )
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            change_link = page_has_link(soup, "Change")
            completed_section = "Have you completed this section?" in soup.text

            if can_edit:
                assert change_link is not None
                assert completed_section is True
            else:
                assert change_link is None
                assert completed_section is False

    def test_get_check_your_answers_with_extracts_add_another(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
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
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )
        submission.data = {
            str(group.id): [
                {str(nested_question_1.id): "First reason"},
                {str(nested_question_1.id): "Second reason"},
            ]
        }

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.check_your_answers",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                section_id=question.form.id,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Check your answers" in soup.text
        assert "Favourite colour details" in soup.text
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

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", True),
        ),
    )
    def test_post_check_your_answers_complete_form(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = client.post(
            url_for(
                "access_grant_funding.check_your_answers",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                section_id=question.form.id,
            ),
            follow_redirects=False,
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            expected_location = url_for(
                "access_grant_funding.tasklist",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
            assert response.location == expected_location


class TestConfirmSentForCertification:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
            ("authenticated_grant_recipient_data_provider_client", True),
        ),
    )
    def test_get_confirm_sent_for_certification(
        self, factories, client_fixture: str, can_access: bool, request: FixtureRequest
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()

        factories.user.create(
            name="Certifier One",
            roles=[
                factories.user_role.create(
                    organisation=grant_recipient.organisation,
                    permissions=[RoleEnum.CERTIFIER],
                )
            ],
        )
        factories.user.create(
            name="Certifier Two",
            roles=[
                factories.user_role.create(
                    organisation=grant_recipient.organisation,
                    permissions=[RoleEnum.CERTIFIER],
                )
            ],
        )
        question = factories.question.create(
            form__title="Colour information",
            form__collection__grant=grant_recipient.grant,
            form__collection__reporting_period_start_date=date(2025, 1, 1),
            form__collection__reporting_period_end_date=date(2025, 6, 1),
            form__collection__submission_period_end_date=date(2025, 12, 31),
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): "Blue"},
            events=[],
        )
        factories.submission_event.create(
            submission=submission,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            related_entity_id=question.form.id,
        )
        factories.submission_event.create(
            submission=submission, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )

        response = client.get(
            url_for(
                "access_grant_funding.confirm_sent_for_certification",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        )
        if can_access:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert (
                "Certifier One or Certifier Two will need to review and sign off the report by "
                "Wednesday 31 December 2025."
            ) in soup.text
        else:
            assert response.status_code == 403

    def test_get_confirm_sent_for_certification_redirects_if_not_sent(
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        question = factories.question.create(
            form__title="Colour information", form__collection__grant=grant_recipient.grant
        )
        submission = factories.submission.create(
            collection=question.form.collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={},
            events=[],
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.confirm_sent_for_certification",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        )
        assert response.status_code == 302
        expected_location = url_for(
            "access_grant_funding.tasklist",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
        )
        assert response.location == expected_location


class TestRemoveAddAnotherEntry:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", True),
        ),
    )
    def test_get_remove_add_another_entry(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
        )
        q1 = factories.question.create(form=group.form, parent=group, name="Question 1")
        q2 = factories.question.create(form=group.form, parent=group, name="Question 2")
        submission = factories.submission.create(
            collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        group.presentation_options = QuestionPresentationOptions(add_another_summary_line_question_ids=[q1.id])
        submission.data = {
            str(group.id): [
                {str(q1.id): "Entry 1", str(q2.id): "Details 1"},
                {str(q1.id): "Entry 2", str(q2.id): "Details 2"},
            ]
        }

        response = client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
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

    def test_get_remove_add_another_entry_with_no_summary(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
        )
        q1 = factories.question.create(form=group.form, parent=group, name="Question 1", text="Question 1")
        submission = factories.submission.create(
            collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        submission.data = {str(group.id): [{}]}

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=0,
                action="remove",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Are you sure you want to remove answer 1?"

    def test_post_remove_add_another_entry_confirms_yes(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
        )
        q1 = factories.question.create(form=group.form, parent=group)
        q2 = factories.question.create(form=group.form, parent=group)
        submission = factories.submission.create(
            collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        submission.data = {
            str(group.id): [
                {str(q1.id): "Entry 1", str(q2.id): "Details 1"},
                {str(q1.id): "Entry 2", str(q2.id): "Details 2"},
                {str(q1.id): "Entry 3", str(q2.id): "Details 3"},
            ]
        }

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=1,
                action="remove",
            ),
            data={"confirm_remove": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        # redirect to the add another summary page (add another group with no index)
        expected_location = url_for(
            "access_grant_funding.ask_a_question",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            question_id=q1.id,
        )
        assert response.location == expected_location

        # this is synced by the ORM from the latest session
        assert len(submission.data[str(group.id)]) == 2
        assert submission.data[str(group.id)][1][str(q1.id)] == "Entry 3"

    def test_post_remove_add_another_entry_confirms_no(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        group = factories.group.create(
            add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
        )
        q1 = factories.question.create(form=group.form, parent=group)
        submission = factories.submission.create(
            collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        submission.data = {str(group.id): [{str(q1.id): "Entry 1"}, {str(q1.id): "Entry 2"}]}

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.ask_a_question",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
                question_id=q1.id,
                add_another_index=0,
                action="remove",
            ),
            data={"confirm_remove": "no"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        # redirect to the add another summary page (add another group with no index)
        expected_location = url_for(
            "access_grant_funding.ask_a_question",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            submission_id=submission.id,
            question_id=q1.id,
        )
        assert response.location == expected_location

        assert len(submission.data[str(group.id)]) == 2
        assert submission.data[str(group.id)][0][str(q1.id)] == "Entry 1"
