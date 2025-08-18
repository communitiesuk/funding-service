import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.types import ExpressionType, SubmissionModeEnum
from tests.utils import get_h1_text


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
        question = factories.question.create(form__title="Colour information", form__section__collection__grant=grant)
        submission = factories.submission.create(collection=question.form.section.collection, created_by=client.user)

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

    @pytest.mark.parametrize(
        "client_fixture",
        (
            ("authenticated_no_role_client"),
            ("authenticated_grant_member_client"),
            ("authenticated_grant_admin_client"),
        ),
    )
    def test_get_other_users_submission_tasklist_403s(self, request: FixtureRequest, client_fixture: str, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(form__title="Colour information", form__section__collection__grant=grant)

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(
            collection=question.form.section.collection, created_by=generic_user
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.submission_tasklist",
                grant_id=grant.id,
                submission_id=generic_submission.id,
            )
        )
        assert response.status_code == 403

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
        question = factories.question.create(form__title="Colour information", form__section__collection__grant=grant)
        submission_data = {str(question.id): "test answer"}
        submission = factories.submission.create(
            collection=question.form.section.collection, created_by=client.user, data=submission_data
        )
        factories.submission_event.create(created_by=client.user, submission=submission, form=question.form)

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
                collection_id=question.form.section.collection.id,
                finished=1,
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
    def test_post_submission_tasklist_live(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(form__title="Colour information", form__section__collection__grant=grant)
        submission_data = {str(question.id): "test answer"}
        submission = factories.submission.create(
            collection=question.form.section.collection,
            mode=SubmissionModeEnum.LIVE,
            created_by=client.user,
            data=submission_data,
        )
        factories.submission_event.create(created_by=client.user, submission=submission, form=question.form)

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
                "deliver_grant_funding.list_report_tasks",
                grant_id=grant.id,
                report_id=submission.collection.id,
            )
            assert response.location == expected_location


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
            form__section__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.section.collection, created_by=client.user)

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
        "client_fixture",
        (
            ("authenticated_no_role_client"),
            ("authenticated_grant_member_client"),
            ("authenticated_grant_admin_client"),
        ),
    )
    def test_get_other_users_ask_a_question_403s(self, request: FixtureRequest, client_fixture: str, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__section__collection__grant=grant,
        )

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(
            collection=question.form.section.collection, created_by=generic_user
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.ask_a_question",
                grant_id=grant.id,
                submission_id=generic_submission.id,
                question_id=question.id,
            )
        )
        assert response.status_code == 403

    def test_get_ask_a_question_with_failing_condition_redirects(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        user = authenticated_grant_admin_client.user
        question = factories.question.create(form__section__collection__grant=grant)
        submission = factories.submission.create(collection=question.form.section.collection, created_by=user)

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
        factories.expression.create(question=question, type=ExpressionType.CONDITION, statement="False")

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
            form__section__collection__grant=grant,
        )
        question_2 = factories.question.create(
            text="What's your least favourite colour?",
            order=1,
            form=question.form,
        )
        submission = factories.submission.create(collection=question.form.section.collection, created_by=client.user)

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

    def test_question_without_guidance_uses_question_as_heading(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading=None,
            guidance_body=None,
            form__section__collection__grant=authenticated_grant_admin_client.grant,
        )
        submission = factories.submission.create(
            collection=question.form.section.collection, created_by=authenticated_grant_admin_client.user
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
            form__section__collection__grant=authenticated_grant_admin_client.grant,
        )
        submission = factories.submission.create(
            collection=question.form.section.collection, created_by=authenticated_grant_admin_client.user
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
            form__section__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.section.collection, created_by=client.user)

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

    @pytest.mark.parametrize(
        "client_fixture",
        (
            ("authenticated_no_role_client"),
            ("authenticated_grant_member_client"),
            ("authenticated_grant_admin_client"),
        ),
    )
    def test_get_other_users_check_your_answers_403s(self, request: FixtureRequest, client_fixture: str, factories):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        question = factories.question.create(
            text="What's your favourite colour?",
            form__title="Colour information",
            form__section__collection__grant=grant,
        )

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(
            collection=question.form.section.collection, created_by=generic_user
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.check_your_answers",
                grant_id=grant.id,
                submission_id=generic_submission.id,
                form_id=question.form.id,
            )
        )
        assert response.status_code == 403

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
            form__section__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.section.collection, created_by=client.user)

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
            form__section__collection__grant=grant,
        )
        submission = factories.submission.create(collection=question.form.section.collection, created_by=client.user)

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
                collection_id=question.form.section.collection.id,
                finished=1,
            )
            assert response.location == expected_location
