import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.types import ExpressionType, QuestionPresentationOptions, SubmissionModeEnum
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
        question = factories.question.create(form__title="Colour information", form__collection__grant=grant)

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(collection=question.form.collection, created_by=generic_user)

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
        question = factories.question.create(form__title="Colour information", form__collection__grant=grant)
        submission_data = {str(question.id): "test answer"}
        submission = factories.submission.create(
            collection=question.form.collection, created_by=client.user, data=submission_data
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
                collection_id=question.form.collection.id,
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
        question = factories.question.create(form__title="Colour information", form__collection__grant=grant)
        submission_data = {str(question.id): "test answer"}
        submission = factories.submission.create(
            collection=question.form.collection,
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
            form__collection__grant=grant,
        )

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(collection=question.form.collection, created_by=generic_user)

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
            assert "Add the first test groups" in soup.text

            # because there's no data we should be configured to add the first answer but its not the users choice
            assert "govuk-!-display-none" in soup.find("div", {"class": "govuk-radios"}).get("class")
            assert soup.find("input", {"name": "add_another", "value": "yes"}).get("checked") is not None

        def test_get_ask_a_question_add_another_summary_with_data(self, authenticated_grant_admin_client, factories):
            group = factories.group.create(add_another=True, name="Test groups", text="Test groups")
            q1 = factories.question.create(form=group.form, parent=group)
            q2 = factories.question.create(form=group.form, parent=group)

            submission = factories.submission.create(
                collection=group.form.collection, created_by=authenticated_grant_admin_client.user
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
            form__collection__grant=grant,
        )

        generic_user = factories.user.create()
        generic_submission = factories.submission.create(collection=question.form.collection, created_by=generic_user)

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
