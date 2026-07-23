import io
import json

import click
import pytest
from click import ClickException
from sqlalchemy import select

from app.common.collections.types import SingleChoiceFromListAnswer, TextSingleLineAnswer
from app.common.data.models import Submission
from app.common.data.types import (
    ExpressionType,
    GrantRecipientModeEnum,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionModeEnum,
    TasklistSectionStatusEnum,
)
from app.common.helpers.collections import SubmissionHelper
from app.developers.commands import create_multi_submissions, export_grants, seed_grants
from app.extensions import db
from tests.models import FactoryAnswer


def _unwrap(command):
    fn = command.callback
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


# Unwrap Flask's with_appcontext / click.pass_context wrappers so we can call
# the function directly within the test's existing app context and DB session.
_create_multi_submissions = _unwrap(create_multi_submissions)
_export_grants = _unwrap(export_grants)
_seed_grants = _unwrap(seed_grants)


def _make_csv(rows: list[tuple[str, str]]) -> io.StringIO:
    buf = io.StringIO()
    buf.write("organisation_external_id,submission_name\n")
    for org_id, name in rows:
        buf.write(f"{org_id},{name}\n")
    buf.seek(0)
    return buf


@pytest.fixture()
def collection_with_submission_name(db_session, factories):
    question = factories.question.create(
        data_type=QuestionDataType.RADIOS,
        form__collection__allow_multiple_submissions=True,
        form__collection__multiple_submissions_are_managed_by_service=True,
        data_source__items=[],
    )
    question.data_source.items = [
        factories.data_source_item.create(data_source=question.data_source, key=key, label=label)
        for key, label in [("alpha", "Alpha"), ("beta", "Beta"), ("charlie", "Charlie"), ("gamma", "Gamma")]
    ]
    collection = question.form.collection
    collection.submission_name_question_id = question.id
    db_session.flush()
    return collection


@pytest.fixture()
def system_user(factories):
    return factories.user.create(email="funding-service-system-user@test.communities.gov.uk")


class TestCreateMultiSubmissions:
    def test_creates_submissions_from_csv(
        self, db_session, factories, collection_with_submission_name, system_user, capsys, mocker
    ):
        collection = collection_with_submission_name
        org = factories.organisation.create(external_id="E06000001")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )

        csv_file = _make_csv([("E06000001", "Alpha"), ("E06000001", "Beta")])

        commit_spy = mocker.spy(db.session, "commit")

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        output = capsys.readouterr().out

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        submission_names = {SubmissionHelper(s).submission_name for s in submissions}
        assert submission_names == {"Alpha", "Beta"}

        assert "Created submission 'alpha'" in output
        assert "Created submission 'beta'" in output
        assert "Created 2 submissions" in output

        commit_spy.assert_called()

    def test_skips_duplicate_submission_names(
        self, db_session, factories, collection_with_submission_name, system_user, capsys
    ):
        collection = collection_with_submission_name
        question = collection.submission_name_question
        org = factories.organisation.create(external_id="E06000001")
        grant_recipient = factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            answers=[FactoryAnswer(question, SingleChoiceFromListAnswer(key="alpha", label="Alpha"))],
        )

        csv_file = _make_csv([("E06000001", "Alpha"), ("E06000001", "Beta")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        output = capsys.readouterr().out

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        assert len(submissions) == 2

        assert "Skipping 'alpha'" in output
        assert "Created submission 'beta'" in output

    def test_dry_run_does_not_commit(
        self, db_session, factories, collection_with_submission_name, system_user, capsys, mocker
    ):
        collection = collection_with_submission_name
        org = factories.organisation.create(external_id="E06000001")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )

        csv_file = _make_csv([("E06000001", "Alpha")])

        commit_spy = mocker.spy(db.session, "commit")

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=False,
        )

        output = capsys.readouterr().out

        commit_spy.assert_not_called()
        assert "Dry run:" in output
        assert "Would create 1 submissions, would skip 0." in output

    def test_warns_about_missing_and_extra_orgs(
        self, db_session, factories, collection_with_submission_name, system_user, capsys
    ):
        collection = collection_with_submission_name
        org1 = factories.organisation.create(external_id="E06000001")
        org2 = factories.organisation.create(external_id="E06000002")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org1,
        )
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org2,
        )

        csv_file = _make_csv([("E06000001", "Alpha"), ("E06000999", "Gamma")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        output = capsys.readouterr().out

        assert "E06000002" in output
        assert "not in CSV" in output
        assert "E06000999" in output
        assert "not matching any grant recipient" in output

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        submission_names = {SubmissionHelper(s).submission_name for s in submissions}
        assert submission_names == {"Alpha"}

    def test_aborts_when_no_submission_name_question(self, db_session, factories, system_user, capsys):
        collection = factories.collection.create(allow_multiple_submissions=True)

        csv_file = _make_csv([("E06000001", "Alpha")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        output = capsys.readouterr().out
        assert "ERROR: Collection does not have a submission name question configured." in output

    def test_aborts_when_user_not_found(self, db_session, factories, collection_with_submission_name, capsys):
        collection = collection_with_submission_name

        csv_file = _make_csv([("E06000001", "Alpha")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address="nonexistent@example.com",
            commit=True,
        )

        output = capsys.readouterr().out
        assert "ERROR: Could not find user" in output

    def test_handles_multiple_orgs(self, db_session, factories, collection_with_submission_name, system_user, capsys):
        collection = collection_with_submission_name
        org1 = factories.organisation.create(external_id="E06000001")
        org2 = factories.organisation.create(external_id="E06000002")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org1,
        )
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org2,
        )

        csv_file = _make_csv(
            [
                ("E06000001", "Alpha"),
                ("E06000001", "Beta"),
                ("E06000002", "Gamma"),
            ]
        )

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        output = capsys.readouterr().out

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        submission_names = {SubmissionHelper(s).submission_name for s in submissions}
        assert submission_names == {"Alpha", "Beta", "Gamma"}

        assert "Created 3 submissions" in output

    @pytest.mark.parametrize("has_other_questions", [True, False])
    def test_marks_submission_name_section_as_complete_if_only_question_in_section(
        self, db_session, factories, collection_with_submission_name, system_user, capsys, has_other_questions
    ):
        collection = collection_with_submission_name
        question = collection.submission_name_question

        if has_other_questions:
            factories.question.create(form=question.form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

        org = factories.organisation.create(external_id="E06000001")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )

        csv_file = _make_csv([("E06000001", "Alpha")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        assert len(submissions) == 1

        helper = SubmissionHelper(submissions[0])
        if has_other_questions:
            assert helper.get_status_for_form(question.form) != TasklistSectionStatusEnum.COMPLETED
        else:
            assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED

    @pytest.mark.parametrize("has_other_questions", [True, False])
    def test_marks_submission_name_section_as_complete_if_only_question_in_section_for_existing_submissions(
        self, db_session, factories, collection_with_submission_name, system_user, capsys, has_other_questions
    ):
        collection = collection_with_submission_name
        question = collection.submission_name_question

        if has_other_questions:
            factories.question.create(form=question.form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

        org = factories.organisation.create(external_id="E06000001")
        grant_recipient = factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            answers=[FactoryAnswer(question, SingleChoiceFromListAnswer(key="alpha", label="Alpha"))],
        )

        csv_file = _make_csv([("E06000001", "Alpha"), ("E06000001", "Beta")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        assert len(submissions) == 2

        for submission in submissions:
            helper = SubmissionHelper(submission)
            if has_other_questions:
                assert helper.cached_get_all_questions_are_answered_for_form(question.form).all_answered is False
                assert helper.get_status_for_form(question.form) != TasklistSectionStatusEnum.COMPLETED
            else:
                assert helper.cached_get_all_questions_are_answered_for_form(question.form).all_answered is True
                assert helper.get_status_for_form(question.form) == TasklistSectionStatusEnum.COMPLETED

    def test_does_not_mark_submission_section_as_complete_if_existing_submission_with_other_questions_all_answered(
        self, db_session, factories, collection_with_submission_name, system_user, capsys
    ):
        collection = collection_with_submission_name
        question = collection.submission_name_question

        q2 = factories.question.create(form=question.form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

        org = factories.organisation.create(external_id="E06000001")
        grant_recipient = factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            answers=[
                FactoryAnswer(question, SingleChoiceFromListAnswer(key="alpha", label="Alpha")),
                FactoryAnswer(q2, TextSingleLineAnswer("Other answer")),
            ],
        )

        csv_file = _make_csv([("E06000001", "Alpha")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        submission = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().one()
        )

        helper = SubmissionHelper(submission)
        assert helper.cached_get_all_questions_are_answered_for_form(question.form).all_answered is True
        assert helper.get_status_for_form(question.form) != TasklistSectionStatusEnum.COMPLETED


def _extract_stdout_json(captured_out: str) -> dict:
    start = captured_out.index("{")
    end = captured_out.rindex("}") + 1
    return json.loads(captured_out[start:end])


class TestExportGrants:
    def test_export_output_sorts_grants_and_json_keys(self, db_session, factories, capsys):
        community_transport_grant = factories.grant.create(name="Community Transport Fund")
        affordable_housing_grant = factories.grant.create(name="Affordable Housing Fund")
        collection = factories.collection.create(grant=affordable_housing_grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(
            form=form,
            presentation_options=QuestionPresentationOptions.model_validate({"suffix": "kg", "prefix": "£"}),
        )
        factories.expression.create(
            question=question,
            context={"z_key": "last", "a_key": "first"},
            statement="True",
            type_=ExpressionType.CONDITION,
        )

        _export_grants(
            grant_ids=[community_transport_grant.id, affordable_housing_grant.id],
            output="stdout",
            email_address=None,
            exclude_users=True,
        )

        captured = capsys.readouterr().out
        payload = _extract_stdout_json(captured)

        assert [grant_data["grant"]["name"] for grant_data in payload["grants"]] == [
            "Affordable Housing Fund",
            "Community Transport Fund",
        ]
        assert captured.index('"a_key"') < captured.index('"z_key"')

    def test_exclude_users_collapses_to_placeholder(self, db_session, factories, capsys):
        question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        grant = question.form.collection.grant

        _export_grants(grant_ids=[grant.id], output="stdout", email_address=None, exclude_users=True)

        payload = _extract_stdout_json(capsys.readouterr().out)

        assert payload["users"] == [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "email": "placeholder@communities.test.gov.localhost",
                "name": "Placeholder User",
            }
        ]
        assert payload["user_roles"] == []

        grant_data = payload["grants"][0]
        assert grant_data["collections"][0]["created_by_id"] == "00000000-0000-0000-0000-000000000001"

    def test_export_output_sorts_user_roles_after_replacing_platform_organisation_id(
        self, db_session, factories, capsys
    ):
        question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        grant = question.form.collection.grant
        user = factories.user.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)

        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )
        factories.user_role.create(
            user=user,
            organisation=grant.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER],
        )

        _export_grants(grant_ids=[grant.id], output="stdout", email_address=None, exclude_users=False)

        payload = _extract_stdout_json(capsys.readouterr().out)
        user_roles = [role for role in payload["user_roles"] if role["user_id"] == str(user.id)]

        assert [role["organisation_id"] for role in user_roles] == [
            str(grant_recipient.organisation_id),
            "<UUID:GB-GOV-27>",
        ]

    def test_production_forces_exclude_users_and_warns_on_opt_out(
        self, app, monkeypatch, db_session, factories, capsys
    ):
        question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        grant = question.form.collection.grant
        monkeypatch.setitem(app.config, "IS_PRODUCTION", True)

        _export_grants(grant_ids=[grant.id], output="stdout", email_address=None, exclude_users=False)

        captured = capsys.readouterr().out
        assert "--no-exclude-users is ignored in production" in captured

        payload = _extract_stdout_json(captured)
        assert [u["id"] for u in payload["users"]] == ["00000000-0000-0000-0000-000000000001"]
        assert payload["grants"][0]["collections"][0]["created_by_id"] == "00000000-0000-0000-0000-000000000001"

    def test_email_output_sends_export(self, db_session, factories, mock_notification_service_calls, capsys):
        question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        grant = question.form.collection.grant

        _export_grants(
            grant_ids=[grant.id],
            output="email",
            email_address="dev@test.communities.gov.uk",
            exclude_users=True,
        )

        assert len(mock_notification_service_calls) == 1
        call = mock_notification_service_calls[0]
        assert call.args[0] == "dev@test.communities.gov.uk"
        assert call.kwargs["personalisation"]["link_to_file"]["filename"] == "grants.json"
        assert "Emailed 1 grants to dev@test.communities.gov.uk" in capsys.readouterr().out

    def test_cannot_export_to_external_email(self, factories):
        question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        grant = question.form.collection.grant

        with pytest.raises(ClickException, match="Cannot send grant export to external email address"):
            _export_grants(
                grant_ids=[grant.id],
                output="email",
                email_address="dev@gmail.com",
                exclude_users=True,
            )

    def test_email_output_requires_email(self, db_session, factories):
        question = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        grant = question.form.collection.grant

        with pytest.raises(click.ClickException, match="--email is required"):
            _export_grants(grant_ids=[grant.id], output="email", email_address=None, exclude_users=True)


class TestSeedGrants:
    def test_refuses_to_run_in_production(self, app, monkeypatch, tmp_path):
        monkeypatch.setitem(app.config, "IS_PRODUCTION", True)
        export_file = tmp_path / "grants.json"
        export_file.write_text("{}")
        with pytest.raises(click.ClickException, match="must not be run in production"):
            _seed_grants(file=export_file)
