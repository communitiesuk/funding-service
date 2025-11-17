import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data import interfaces
from app.common.data.types import (
    ExpressionType,
    ManagedExpressionsEnum,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventKey,
    SubmissionModeEnum,
)
from tests.utils import get_h1_text


def _get_or_create_grant_recipient(organisation, grant, factories):
    """Get existing grant_recipient or create one if it doesn't exist."""
    try:
        return interfaces.grant_recipients.get_grant_recipient(grant.id, organisation.id)
    except Exception:
        # If it doesn't exist, create it
        return factories.grant_recipient.create(organisation=organisation, grant=grant)


class TestTasklist:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_tasklist(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            form__title="Colour information", form__collection__grant=grant_recipient.grant
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

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_post_tasklist_complete_submission(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories
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
            form=question.form,
            key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED,
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

            # todo: this will be the submission confirmation/ awaiting sign off page
            expected_location = (
                f"/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}"
                f"/reports/{submission.id}"
            )
            assert response.location == expected_location


class TestAskAQuestion:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_ask_a_question(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        question = factories.question.create(
            form__title="Colour information", form__collection__grant=grant_recipient.grant
        )
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
        self, show_on_same_page: bool, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
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
        response = authenticated_grant_recipient_member_client.get(
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
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
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
            created_by=authenticated_grant_recipient_member_client.user,
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
        response = authenticated_grant_recipient_member_client.get(
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
        response = authenticated_grant_recipient_member_client.get(
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
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        question = factories.question.create(form__collection__grant=grant_recipient.grant)
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_member_client.get(
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

        response = authenticated_grant_recipient_member_client.get(
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
            ("authenticated_grant_recipient_member_client", True),
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

    def test_post_ask_a_question_add_another_context(self, authenticated_grant_recipient_member_client, factories):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
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
        response = authenticated_grant_recipient_member_client.post(
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
        response = authenticated_grant_recipient_member_client.post(
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
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading=None,
            guidance_body=None,
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_member_client.get(
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

    def test_question_with_guidance_uses_guidance_heading(self, authenticated_grant_recipient_member_client, factories):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        question = factories.question.create(
            text="What's your favourite colour?",
            guidance_heading="Important instructions",
            guidance_body="Please read this carefully before answering",
            form__collection__grant=grant_recipient.grant,
        )
        submission = factories.submission.create(
            collection=question.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_member_client.get(
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
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
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

        response = authenticated_grant_recipient_member_client.get(
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
        def test_get_add_another_summary_empty(self, authenticated_grant_recipient_member_client, factories):
            grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
            group = factories.group.create(
                add_another=True, name="Test groups", text="Test groups", form__collection__grant=grant_recipient.grant
            )
            q1 = factories.question.create(form=group.form, parent=group)
            _ = factories.question.create(form=group.form, parent=group)
            submission = factories.submission.create(
                collection=group.form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
            )

            response = authenticated_grant_recipient_member_client.get(
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
            self, authenticated_grant_recipient_member_client, factories
        ):
            grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
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

            response = authenticated_grant_recipient_member_client.get(
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

            # do you want to add another component is shown and defaults to nothing selected
            assert "govuk-!-display-none" not in soup.find("div", {"class": "govuk-radios"}).get("class")
            assert soup.find("input", {"name": "add_another", "value": "yes"}).get("checked") is None
            assert soup.find("input", {"name": "add_another", "value": "no"}).get("checked") is None


class TestCheckYourAnswers:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_check_your_answers(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
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

    def test_get_check_your_answers_with_extracts_add_another(
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
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

        response = authenticated_grant_recipient_member_client.get(
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
            ("authenticated_grant_recipient_member_client", True),
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
