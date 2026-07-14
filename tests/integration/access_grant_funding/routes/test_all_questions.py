import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.types import (
    ExpressionType,
    ManagedExpressionsEnum,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionModeEnum,
)
from app.common.expressions.references import ExpressionReference


class TestAllQuestions:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_access_control(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        submission = factories.submission.create(
            grant_recipient=grant_recipient, collection__grant=grant_recipient.grant, mode=SubmissionModeEnum.LIVE
        )

        response = client.get(
            url_for(
                "access_grant_funding.all_questions",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_type=submission.collection.type,
                submission_id=submission.id,
            ),
        )

        assert response.status_code == (200 if can_access else 403)

    def test_page_lists_sections_questions_groups_settings_and_conditions(
        self, authenticated_grant_recipient_member_client, factories
    ):
        client = authenticated_grant_recipient_member_client
        grant_recipient = client.grant_recipient

        form = factories.form.create(title="Project details", collection__grant=grant_recipient.grant)

        factories.question.create(
            form=form,
            order=0,
            data_type=QuestionDataType.TEXT_MULTI_LINE,
            text="Describe your project",
            presentation_options=QuestionPresentationOptions(word_limit=200),
        )
        favourite_colour = factories.question.create(
            form=form, order=1, data_type=QuestionDataType.YES_NO, text="Do you have a favourite colour?"
        )
        radios = factories.question.create(form=form, order=2, data_type=QuestionDataType.RADIOS, text="Pick an option")

        group = factories.group.create(form=form, order=3, name="Match funding", add_another=True)
        conditional_question = factories.question.create(
            form=form, parent=group, text="How much match funding do you have?"
        )
        factories.expression.create(
            question=conditional_question,
            created_by=client.user,
            type_=ExpressionType.CONDITION,
            context={"subject_reference": ExpressionReference.from_question(favourite_colour)},
            statement=f"{favourite_colour.safe_qid} is True",
            managed_name=ManagedExpressionsEnum.IS_YES,
        )

        submission = factories.submission.create(
            collection=form.collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = client.get(
            url_for(
                "access_grant_funding.all_questions",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_type=submission.collection.type,
                submission_id=submission.id,
            ),
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Page furniture
        assert "View all questions" in text
        assert form.collection.name in text
        assert "Project details" in text  # section heading

        # Question text + settings suffix
        assert "Describe your project" in text
        assert "(200 words)" in text

        # Radio options are listed out
        for item in radios.data_source.items:
            assert item.label in text

        # Group name, repeatable indicator, and its nested question
        assert "Match funding" in text
        assert "Can be added more than once" in text
        assert "How much match funding do you have?" in text

        # Condition tag on the nested question
        assert "Only applicable if" in text
        assert favourite_colour.name in text

        # Back link
        assert f"Back to {submission.collection.type.constants.singular}" in text
