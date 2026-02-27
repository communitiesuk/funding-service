import io

import pytest
from sqlalchemy import select

from app.common.data.models import Submission
from app.common.data.types import (
    GrantRecipientModeEnum,
    QuestionDataType,
    SubmissionModeEnum,
    TasklistSectionStatusEnum,
)
from app.common.helpers.collections import SubmissionHelper
from app.developers.commands import create_multi_submissions
from app.extensions import db

# Unwrap Flask's with_appcontext / click.pass_context wrappers so we can call
# the function directly within the test's existing app context and DB session.
_create_multi_submissions = create_multi_submissions.callback
while hasattr(_create_multi_submissions, "__wrapped__"):
    _create_multi_submissions = _create_multi_submissions.__wrapped__


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
        org = factories.organisation.create(external_id="ORG-001")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )

        csv_file = _make_csv([("ORG-001", "Alpha"), ("ORG-001", "Beta")])

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
        org = factories.organisation.create(external_id="ORG-001")
        grant_recipient = factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): {"key": "alpha", "label": "Alpha"}},
        )

        csv_file = _make_csv([("ORG-001", "Alpha"), ("ORG-001", "Beta")])

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
        org = factories.organisation.create(external_id="ORG-001")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )

        csv_file = _make_csv([("ORG-001", "Alpha")])

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
        org1 = factories.organisation.create(external_id="ORG-001")
        org2 = factories.organisation.create(external_id="ORG-002")
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

        csv_file = _make_csv([("ORG-001", "Alpha"), ("ORG-999", "Gamma")])

        _create_multi_submissions(
            collection_id=collection.id,
            mode=GrantRecipientModeEnum.LIVE,
            file=csv_file,
            service_user_email_address=system_user.email,
            commit=True,
        )

        output = capsys.readouterr().out

        assert "ORG-002" in output
        assert "not in CSV" in output
        assert "ORG-999" in output
        assert "not matching any grant recipient" in output

        submissions = (
            db_session.execute(select(Submission).where(Submission.collection_id == collection.id)).scalars().all()
        )
        submission_names = {SubmissionHelper(s).submission_name for s in submissions}
        assert submission_names == {"Alpha"}

    def test_aborts_when_no_submission_name_question(self, db_session, factories, system_user, capsys):
        collection = factories.collection.create(allow_multiple_submissions=True)

        csv_file = _make_csv([("ORG-001", "Alpha")])

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

        csv_file = _make_csv([("ORG-001", "Alpha")])

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
        org1 = factories.organisation.create(external_id="ORG-001")
        org2 = factories.organisation.create(external_id="ORG-002")
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
                ("ORG-001", "Alpha"),
                ("ORG-001", "Beta"),
                ("ORG-002", "Gamma"),
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

        org = factories.organisation.create(external_id="ORG-001")
        factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )

        csv_file = _make_csv([("ORG-001", "Alpha")])

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

        org = factories.organisation.create(external_id="ORG-001")
        grant_recipient = factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): {"key": "alpha", "label": "Alpha"}},
        )

        csv_file = _make_csv([("ORG-001", "Alpha"), ("ORG-001", "Beta")])

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

        org = factories.organisation.create(external_id="ORG-001")
        grant_recipient = factories.grant_recipient.create(
            mode=GrantRecipientModeEnum.LIVE,
            grant=collection.grant,
            organisation=org,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): {"key": "alpha", "label": "Alpha"}, str(q2.id): "Other answer"},
        )

        csv_file = _make_csv([("ORG-001", "Alpha")])

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
