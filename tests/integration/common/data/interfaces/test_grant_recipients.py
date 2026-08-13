import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import NoResultFound

from app.common.collections.types import TextSingleLineAnswer
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipient,
    create_grant_recipients,
    delete_grant_recipients,
    get_grant_recipient,
    get_grant_recipient_data_provider_roles,
    get_grant_recipient_data_providers_count,
    get_grant_recipient_or_none,
    get_grant_recipients,
    get_grant_recipients_count,
    get_grant_recipients_for_collection_with_locked_submissions,
    get_grant_recipients_for_organisation,
    get_grant_recipients_with_outstanding_submissions_for_collection,
    get_or_create_grant_recipient,
    get_or_create_grant_recipient_pair,
)
from app.common.data.models import GrantRecipient
from app.common.data.types import (
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    OrganisationModeEnum,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from tests.models import FactoryAnswer


class TestGetGrantRecipients:
    def test_returns_grant_recipients_for_grant(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)
        factories.grant_recipient.create(grant=grant, organisation=org3)

        result = get_grant_recipients(grant)

        assert len(result) == 3
        assert {gr.organisation_id for gr in result} == {org1.id, org2.id, org3.id}

    def test_returns_only_grant_recipients_for_specified_grant(self, factories, db_session):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")

        gr1 = factories.grant_recipient.create(grant=grant1, organisation=org1)
        factories.grant_recipient.create(grant=grant2, organisation=org2)

        result = get_grant_recipients(grant1)

        assert len(result) == 1
        assert result[0].id == gr1.id

    def test_returns_empty_list_when_no_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()

        result = get_grant_recipients(grant)

        assert result == []

    def test_without_data_providers_parameter_does_not_eager_load(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        db_session.expire_all()

        result = get_grant_recipients(grant)

        with track_sql_queries() as queries:
            assert len(result[0].data_providers) == 1

        assert len(queries) == 1

    def test_with_data_providers_false_does_not_eager_load(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        db_session.expire_all()

        result = get_grant_recipients(grant, with_data_providers=False)

        with track_sql_queries() as queries:
            assert len(result[0].data_providers) == 1

        assert len(queries) == 1

    def test_with_data_providers_true_eager_loads_relationship(self, factories, db_session, track_sql_queries):
        grant_recipient = factories.grant_recipient.create()
        factories.user_role.create(
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        db_session.expire_all()
        _ = grant_recipient.grant

        with track_sql_queries() as queries:
            result = get_grant_recipients(grant_recipient.grant, with_data_providers=True)

        assert len(queries) == 1

        with track_sql_queries() as queries:
            data_providers = result[0].data_providers
            assert len(data_providers) == 1

        assert len(queries) == 0

    def test_with_data_providers_true_with_multiple_grant_recipients_does_not_cause_n_plus_1(
        self, factories, db_session, track_sql_queries
    ):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        for gr in grant_recipients:
            factories.user_role.create_batch(
                3,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )

        db_session.expire_all()
        _ = [gr.grant for gr in grant_recipients]

        with track_sql_queries() as queries:
            result = get_grant_recipients(grant, with_data_providers=True)

        assert len(queries) == 1

        with track_sql_queries() as queries:
            for gr in result:
                assert len(gr.data_providers) == 3

        assert len(queries) == 0

    def test_with_data_providers_true_handles_no_data_providers(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        db_session.expire_all()

        result = get_grant_recipients(grant, with_data_providers=True)

        with track_sql_queries() as queries:
            assert result[0].data_providers == []

        assert len(queries) == 0

    def test_without_certifiers_parameter_does_not_eager_load(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        db_session.expire_all()

        result = get_grant_recipients(grant)

        with track_sql_queries() as queries:
            assert len(result[0].certifiers) == 1

        assert len(queries) == 2

    def test_with_certifiers_false_does_not_eager_load(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        db_session.expire_all()

        result = get_grant_recipients(grant, with_certifiers=False)

        with track_sql_queries() as queries:
            assert len(result[0].certifiers) == 1

        assert len(queries) == 2

    def test_with_certifiers_true_eager_loads_relationship(self, factories, db_session, track_sql_queries):
        grant_recipient = factories.grant_recipient.create()
        factories.user_role.create_batch(
            5,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        db_session.expire_all()
        _ = grant_recipient.grant

        with track_sql_queries() as queries:
            result = get_grant_recipients(grant_recipient.grant, with_certifiers=True)

        assert len(queries) == 1

        with track_sql_queries() as queries:
            certifiers = result[0].certifiers
            assert len(certifiers) == 5

        assert len(queries) == 0

    def test_with_certifiers_true_with_multiple_grant_recipients_does_not_cause_n_plus_1(
        self, factories, db_session, track_sql_queries
    ):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        for gr in grant_recipients:
            factories.user_role.create_batch(
                3,
                organisation=gr.organisation,
                grant=gr.grant,
                permissions=[RoleEnum.CERTIFIER],
            )

        db_session.expire_all()
        _ = [gr.grant for gr in grant_recipients]

        with track_sql_queries() as queries:
            result = get_grant_recipients(grant, with_certifiers=True)

        assert len(queries) == 1

        with track_sql_queries() as queries:
            for gr in result:
                assert len(gr.certifiers) == 3

        assert len(queries) == 0

    def test_with_certifiers_true_handles_no_certifiers(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        db_session.expire_all()

        result = get_grant_recipients(grant, with_certifiers=True)

        with track_sql_queries() as queries:
            assert result[0].certifiers == []

        assert len(queries) == 0

    def test_without_organisations_parameter_does_not_eager_load(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        db_session.expire_all()

        result = get_grant_recipients(grant)

        with track_sql_queries() as queries:
            assert result[0].organisation is not None

        assert len(queries) == 1

    def test_with_organisations_false_does_not_eager_load(self, factories, db_session, track_sql_queries):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        db_session.expire_all()

        result = get_grant_recipients(grant, with_organisations=False)

        with track_sql_queries() as queries:
            assert result[0].organisation is not None

        assert len(queries) == 1

    def test_with_organisations_true_eager_loads_relationship(self, factories, db_session, track_sql_queries):
        grant_recipient = factories.grant_recipient.create()
        db_session.expire_all()
        _ = grant_recipient.grant

        with track_sql_queries() as queries:
            result = get_grant_recipients(grant_recipient.grant, with_organisations=True)

        # 1 for grant recipients
        # 1 selectin organisations
        assert len(queries) == 2

        with track_sql_queries() as queries:
            assert result[0].organisation is not None

        assert len(queries) == 0

    def test_with_organisations_true_with_multiple_grant_recipients_does_not_cause_n_plus_1(
        self, factories, db_session, track_sql_queries
    ):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        db_session.expire_all()
        _ = [gr.grant for gr in grant_recipients]

        with track_sql_queries() as queries:
            result = get_grant_recipients(grant, with_organisations=True)

        # 1 for grant recipients
        # 1 selectin organisations
        assert len(queries) == 2

        with track_sql_queries() as queries:
            for gr in result:
                assert gr.organisation is not None

        assert len(queries) == 0


class TestGetGrantRecipientsWithOutstandingReports:
    def test_returns_grant_recipients_for_grant_with_status(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")
        org4 = factories.organisation.create(name="Organisation 4")

        gr1 = factories.grant_recipient.create(grant=grant, organisation=org1)
        gr2 = factories.grant_recipient.create(grant=grant, organisation=org2)
        gr3 = factories.grant_recipient.create(grant=grant, organisation=org3)
        factories.grant_recipient.create(grant=grant, organisation=org4)

        question = factories.question.create(form__collection__grant=grant)
        collection = question.form.collection

        # gr1 has sent for certification, not submitted, so should be in the list
        submission1 = factories.submission.create(
            grant_recipient=gr1,
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Blue"))],
        )
        factories.submission_event.create(
            submission=submission1,
            related_entity_id=collection.forms[0].id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )
        factories.submission_event.create(
            submission=submission1, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )
        submission1.status = SubmissionStatusEnum.AWAITING_SIGN_OFF

        # gr2 has submitted so should not be in the list
        submission2 = factories.submission.create(
            grant_recipient=gr2,
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Blue"))],
        )
        factories.submission_event.create(
            submission=submission2,
            related_entity_id=collection.forms[0].id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )
        factories.submission_event.create(submission=submission2, event_type=SubmissionEventType.SUBMISSION_SUBMITTED)
        submission2.status = SubmissionStatusEnum.SUBMITTED

        # gr3 has had their certification declined, so should be in the list
        submission3 = factories.submission.create(
            grant_recipient=gr3,
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Blue"))],
        )
        factories.submission_event.create(
            submission=submission3,
            related_entity_id=collection.forms[0].id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )
        factories.submission_event.create(
            submission=submission3, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )
        factories.submission_event.create(
            submission=submission3, event_type=SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER
        )
        submission3.status = SubmissionStatusEnum.IN_PROGRESS
        # org 4 has not started their report yet so should be in the list

        result = get_grant_recipients_with_outstanding_submissions_for_collection(
            grant, collection_id=collection.id, with_certifiers=True, with_data_providers=True
        )

        assert len(result) == 3
        assert {gr.organisation_id for gr in result} == {org1.id, org3.id, org4.id}


class TestGetGrantRecipientsForOrganisation:
    def test_returns_all_grant_recipients_for_organisation(self, factories, db_session):
        organisation = factories.organisation.create()
        other_organisation = factories.organisation.create()
        grant_a = factories.grant.create()
        grant_b = factories.grant.create()
        grant_c = factories.grant.create()

        factories.grant_recipient.create(grant=grant_a, organisation=organisation)
        factories.grant_recipient.create(grant=grant_b, organisation=organisation)
        factories.grant_recipient.create(grant=grant_c, organisation=other_organisation)

        result = get_grant_recipients_for_organisation(organisation.id)

        assert {gr.grant_id for gr in result} == {grant_a.id, grant_b.id}

    def test_filters_by_mode(self, factories, db_session):
        organisation = factories.organisation.create()
        grant_a = factories.grant.create()
        grant_b = factories.grant.create()

        factories.grant_recipient.create(grant=grant_a, organisation=organisation, mode=GrantRecipientModeEnum.LIVE)
        factories.grant_recipient.create(grant=grant_b, organisation=organisation, mode=GrantRecipientModeEnum.TEST)

        live = get_grant_recipients_for_organisation(organisation.id)
        test = get_grant_recipients_for_organisation(organisation.id, mode=GrantRecipientModeEnum.TEST)

        assert {gr.grant_id for gr in live} == {grant_a.id}
        assert {gr.grant_id for gr in test} == {grant_b.id}

    def test_returns_empty_when_no_recipients(self, factories, db_session):
        organisation = factories.organisation.create()

        assert get_grant_recipients_for_organisation(organisation.id) == []


class TestGetGrantRecipient:
    def test_returns_grant_recipient_for_organisation_and_grant(self, factories, db_session):
        grant = factories.grant.create()
        organisation = factories.organisation.create()
        organisation2 = factories.organisation.create()

        factories.grant_recipient.create(grant=grant, organisation=organisation)

        result = get_grant_recipient(grant.id, organisation.id)
        assert result.grant == grant
        assert result.organisation == organisation

        with pytest.raises(NoResultFound):
            get_grant_recipient(grant.id, organisation2.id)


class TestGetGrantRecipientOrNone:
    def test_returns_grant_recipient_for_organisation_and_grant(self, factories):
        grant = factories.grant.create()
        organisation = factories.organisation.create()

        factories.grant_recipient.create(grant=grant, organisation=organisation)

        result = get_grant_recipient_or_none(grant.id, organisation.id)
        assert result is not None
        assert result.grant == grant
        assert result.organisation == organisation

    def test_returns_none_when_no_grant_recipient_exists(self, factories):
        grant = factories.grant.create()
        organisation = factories.organisation.create()

        assert get_grant_recipient_or_none(grant.id, organisation.id) is None


class TestCreateGrantRecipient:
    def test_creates_grant_recipient_for_organisation(self, factories, db_session):
        grant = factories.grant.create()
        organisation = factories.organisation.create()

        result = create_grant_recipient(grant, organisation, status=GrantRecipientStatusEnum.APPLYING)

        assert result.grant == grant
        assert result.organisation == organisation
        assert result.status == GrantRecipientStatusEnum.APPLYING

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1


class TestGetOrCreateGrantRecipient:
    def test_creates_grant_recipient_when_none_exists(self, factories, db_session):
        grant = factories.grant.create()
        organisation = factories.organisation.create()

        result = get_or_create_grant_recipient(grant, organisation, status=GrantRecipientStatusEnum.APPLYING)

        assert result.grant == grant
        assert result.organisation == organisation
        assert result.status == GrantRecipientStatusEnum.APPLYING

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1

    def test_returns_existing_grant_recipient_without_creating_duplicate(self, factories, db_session):
        grant = factories.grant.create()
        organisation = factories.organisation.create()
        existing = factories.grant_recipient.create(
            grant=grant, organisation=organisation, status=GrantRecipientStatusEnum.APPLYING
        )

        result = get_or_create_grant_recipient(grant, organisation, status=GrantRecipientStatusEnum.APPLYING)

        assert result.id == existing.id

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1


class TestGetOrCreateGrantRecipientPair:
    def test_creates_both_grant_recipients_when_counterpart_organisation_exists(self, factories):
        grant = factories.grant.create()
        live_organisation = factories.organisation.create(external_id="org-1", mode=OrganisationModeEnum.LIVE)
        test_organisation = factories.organisation.create(external_id="org-1", mode=OrganisationModeEnum.TEST)

        pair = get_or_create_grant_recipient_pair(grant, live_organisation, status=GrantRecipientStatusEnum.APPLYING)

        assert pair[OrganisationModeEnum.LIVE] is not None
        assert pair[OrganisationModeEnum.LIVE].organisation == live_organisation
        assert pair[OrganisationModeEnum.LIVE].mode == GrantRecipientModeEnum.LIVE
        assert pair[OrganisationModeEnum.TEST] is not None
        assert pair[OrganisationModeEnum.TEST].organisation == test_organisation
        assert pair[OrganisationModeEnum.TEST].mode == GrantRecipientModeEnum.TEST

    def test_only_creates_one_grant_recipient_when_counterpart_organisation_missing(self, factories, db_session):
        grant = factories.grant.create()
        live_organisation = factories.organisation.create(external_id="org-2", mode=OrganisationModeEnum.LIVE)

        pair = get_or_create_grant_recipient_pair(grant, live_organisation, status=GrantRecipientStatusEnum.APPLYING)

        assert pair[OrganisationModeEnum.LIVE] is not None
        assert pair[OrganisationModeEnum.LIVE].organisation == live_organisation
        assert pair[OrganisationModeEnum.TEST] is None

        grant_recipients = db_session.scalars(select(GrantRecipient).where(GrantRecipient.grant_id == grant.id)).all()
        assert len(grant_recipients) == 1


class TestGetGrantRecipientsCount:
    def test_returns_count_of_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)
        factories.grant_recipient.create(grant=grant, organisation=org3)

        result = get_grant_recipients_count(grant)

        assert result == 3

    def test_returns_zero_when_no_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()

        result = get_grant_recipients_count(grant)

        assert result == 0

    def test_counts_only_grant_recipients_for_specified_grant(self, factories, db_session):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant1, organisation=org1)
        factories.grant_recipient.create(grant=grant2, organisation=org2)
        factories.grant_recipient.create(grant=grant2, organisation=org3)

        result = get_grant_recipients_count(grant1)

        assert result == 1


class TestCreateGrantRecipients:
    def test_creates_grant_recipients_for_organisations(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        create_grant_recipients(grant, [org1.id, org2.id, org3.id], status=GrantRecipientStatusEnum.AWARDED)

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 3
        assert {gr.organisation_id for gr in grant_recipients} == {org1.id, org2.id, org3.id}
        assert all(gr.status == GrantRecipientStatusEnum.AWARDED for gr in grant_recipients)

    def test_creates_single_grant_recipient(self, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(name="Organisation 1")

        create_grant_recipients(grant, [org.id], status=GrantRecipientStatusEnum.AWARDED)

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 1
        assert grant_recipients[0].organisation_id == org.id
        assert grant_recipients[0].grant_id == grant.id
        assert grant_recipients[0].status == GrantRecipientStatusEnum.AWARDED

    def test_creates_grant_recipients_with_given_status(self, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(name="Organisation 1")

        create_grant_recipients(grant, [org.id], status=GrantRecipientStatusEnum.APPLYING)

        db_session.expire_all()
        grant_recipient = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING

    def test_handles_empty_list(self, factories, db_session):
        grant = factories.grant.create()
        initial_count = db_session.query(GrantRecipient).count()

        create_grant_recipients(grant, [], status=GrantRecipientStatusEnum.AWARDED)

        db_session.expire_all()
        final_count = db_session.query(GrantRecipient).count()
        assert final_count == initial_count

    def test_adds_to_existing_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)

        create_grant_recipients(grant, [org2.id, org3.id], status=GrantRecipientStatusEnum.AWARDED)

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 3
        assert {gr.organisation_id for gr in grant_recipients} == {org1.id, org2.id, org3.id}


class TestDeleteGrantRecipients:
    def test_deletes_all_grant_recipients_for_grant(self, factories, db_session):
        grant = factories.grant.create()
        factories.grant_recipient.create_batch(3, grant=grant)

        delete_grant_recipients(grant)

        assert db_session.query(GrantRecipient).filter_by(grant_id=grant.id).count() == 0

    def test_does_not_delete_other_grants_recipients(self, factories, db_session):
        grant = factories.grant.create()
        other_grant = factories.grant.create()
        factories.grant_recipient.create_batch(2, grant=grant)
        other_grant_recipient = factories.grant_recipient.create(grant=other_grant)

        delete_grant_recipients(grant)

        assert db_session.query(GrantRecipient).filter_by(grant_id=grant.id).count() == 0
        assert db_session.get(GrantRecipient, other_grant_recipient.id) is not None


class TestGetGrantRecipientDataProvidersCount:
    def test_no_grant_recipient_users(self, db_session, factories):
        grant = factories.grant.create()

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 0
        assert recipients_missing_data_providers == []

    def test_single_grant_recipient_user(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 1
        assert recipients_missing_data_providers == []

    def test_multiple_grant_recipient_users_same_organisation(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        users = factories.user.create_batch(3)
        for user in users:
            factories.user_role.create(
                user=user,
                organisation=grant_recipient.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 3
        assert recipients_missing_data_providers == []

    def test_multiple_grant_recipient_users_different_organisations(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(2, grant=grant)

        user1 = factories.user.create()
        factories.user_role.create(
            user=user1,
            organisation=grant_recipients[0].organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        user2 = factories.user.create()
        factories.user_role.create(
            user=user2,
            organisation=grant_recipients[1].organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 2
        assert recipients_missing_data_providers == []

    def test_excludes_grant_team_members(self, db_session, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant)

        grant_team_user = factories.user.create()
        factories.user_role.create(
            user=grant_team_user,
            organisation=grant.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 0
        assert recipients_missing_data_providers == [gr.organisation.name]

    def test_excludes_admin_roles(self, db_session, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 0
        assert recipients_missing_data_providers == [gr.organisation.name]

    def test_excludes_users_from_different_grant(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant2,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant1)

        assert count == 0
        assert recipients_missing_data_providers == [grant_recipient.organisation.name]

    def test_deduplicates_users_across_grant_recipients(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient_1 = factories.grant_recipient.create(grant=grant)
        grant_recipient_2 = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient_1.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=user,
            organisation=grant_recipient_2.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        count, recipients_missing_data_providers = get_grant_recipient_data_providers_count(grant)

        assert count == 1
        assert recipients_missing_data_providers == []


class TestGetGrantRecipientDataProviderRoles:
    def test_returns_empty_list_when_no_users(self, db_session, factories):
        grant = factories.grant.create()

        result = get_grant_recipient_data_provider_roles(grant)

        assert result == []

    def test_returns_single_user_role(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create(name="Test User", email="test@example.com")
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        result = get_grant_recipient_data_provider_roles(grant)

        assert len(result) == 1
        assert result[0].user_id == user.id
        assert result[0].organisation_id == grant_recipient.organisation_id
        assert result[0].user.name == "Test User"
        assert result[0].user.email == "test@example.com"
        assert result[0].organisation.name == grant_recipient.organisation.name

    def test_returns_multiple_user_roles_same_organisation(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        users = factories.user.create_batch(3)
        for user in users:
            factories.user_role.create(
                user=user,
                organisation=grant_recipient.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )

        result = get_grant_recipient_data_provider_roles(grant)

        assert len(result) == 3
        user_ids = {ur.user_id for ur in result}
        assert user_ids == {u.id for u in users}
        for ur in result:
            assert ur.organisation_id == grant_recipient.organisation_id

    def test_returns_multiple_user_roles_different_organisations(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(2, grant=grant)

        user1 = factories.user.create(name="User 1")
        user2 = factories.user.create(name="User 2")

        factories.user_role.create(
            user=user1,
            organisation=grant_recipients[0].organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=user2,
            organisation=grant_recipients[1].organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        result = get_grant_recipient_data_provider_roles(grant)

        assert len(result) == 2
        result_dict = {ur.user_id: (ur.organisation_id, ur.user.name) for ur in result}
        assert result_dict[user1.id] == (grant_recipients[0].organisation_id, "User 1")
        assert result_dict[user2.id] == (grant_recipients[1].organisation_id, "User 2")

    def test_excludes_users_from_different_grant(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user1 = factories.user.create()
        user2 = factories.user.create()
        factories.user_role.create(
            user=user1,
            organisation=grant_recipient.organisation,
            grant=grant1,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=user2,
            organisation=grant_recipient.organisation,
            grant=grant2,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        result = get_grant_recipient_data_provider_roles(grant1)

        assert len(result) == 1
        assert result[0].user_id == user1.id

    def test_excludes_non_member_roles(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        member_user = factories.user.create()
        admin_user = factories.user.create()
        factories.user_role.create(
            user=member_user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(user=admin_user, permissions=[RoleEnum.ADMIN])

        result = get_grant_recipient_data_provider_roles(grant)

        assert len(result) == 1
        assert result[0].user_id == member_user.id


class TestGetGrantRecipientsWithLockedSubmissionsForCollection:
    def test_returns_recipients_with_submitted_or_awaiting_sign_off_submissions(
        self, factories, db_session, track_sql_queries
    ):
        grant = factories.grant.create()
        awaiting_sign_off_org = factories.organisation.create(name="Awaiting sign off organisation")
        submitted_org = factories.organisation.create(name="Submitted organisation")
        submitted_with_changes_org = factories.organisation.create(name="Submitted with changes organisation")
        in_progress_org = factories.organisation.create(name="In progress organisation")
        not_started_org = factories.organisation.create(name="Not started organisation")
        wrong_collection_org = factories.organisation.create(name="Wrong collection organisation")
        wrong_mode_org = factories.organisation.create(name="Wrong mode organisation")

        awaiting_sign_off_gr = factories.grant_recipient.create(grant=grant, organisation=awaiting_sign_off_org)
        submitted_gr = factories.grant_recipient.create(grant=grant, organisation=submitted_org)
        submitted_with_changes_gr = factories.grant_recipient.create(
            grant=grant, organisation=submitted_with_changes_org
        )
        in_progress_gr = factories.grant_recipient.create(grant=grant, organisation=in_progress_org)
        factories.grant_recipient.create(grant=grant, organisation=not_started_org)
        wrong_collection_gr = factories.grant_recipient.create(grant=grant, organisation=wrong_collection_org)
        wrong_mode_gr = factories.grant_recipient.create(grant=grant, organisation=wrong_mode_org)

        question = factories.question.create(form__collection__grant=grant)
        collection = question.form.collection
        other_question = factories.question.create(form__collection__grant=grant)
        other_collection = other_question.form.collection

        for grant_recipient, status, submission_mode, submission_collection, answer_question in [
            (
                awaiting_sign_off_gr,
                SubmissionStatusEnum.AWAITING_SIGN_OFF,
                SubmissionModeEnum.LIVE,
                collection,
                question,
            ),
            (submitted_gr, SubmissionStatusEnum.SUBMITTED, SubmissionModeEnum.LIVE, collection, question),
            (
                submitted_with_changes_gr,
                SubmissionStatusEnum.SUBMITTED_WITH_CHANGES,
                SubmissionModeEnum.LIVE,
                collection,
                question,
            ),
            (in_progress_gr, SubmissionStatusEnum.IN_PROGRESS, SubmissionModeEnum.LIVE, collection, question),
            (
                wrong_collection_gr,
                SubmissionStatusEnum.SUBMITTED,
                SubmissionModeEnum.LIVE,
                other_collection,
                other_question,
            ),
            (wrong_mode_gr, SubmissionStatusEnum.SUBMITTED, SubmissionModeEnum.TEST, collection, question),
        ]:
            submission = factories.submission.create(
                grant_recipient=grant_recipient,
                collection=submission_collection,
                mode=submission_mode,
                answers=[FactoryAnswer(answer_question, TextSingleLineAnswer("Blue"))],
            )
            submission.status = status
            factories.submission_event.create(
                submission=submission,
                related_entity_id=submission_collection.forms[0].id,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            )

        db_session.expire_all()
        with track_sql_queries() as queries:
            result = get_grant_recipients_for_collection_with_locked_submissions(
                grant, collection_id=collection.id, submission_mode=SubmissionModeEnum.LIVE
            )

        assert {gr.organisation_id for gr in result} == {
            awaiting_sign_off_org.id,
            submitted_org.id,
            submitted_with_changes_org.id,
        }
        # collection, grant, grant_recipient, organisation
        assert len(queries) == 4
