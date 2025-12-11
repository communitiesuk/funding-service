import pytest
from sqlalchemy.orm.exc import NoResultFound

from app.common.data.interfaces.grant_recipients import (
    all_grant_recipients_have_data_providers,
    create_grant_recipients,
    get_grant_recipient,
    get_grant_recipient_data_provider_roles,
    get_grant_recipient_data_providers_count,
    get_grant_recipients,
    get_grant_recipients_count,
    get_grant_recipients_with_outstanding_submissions_for_collection,
)
from app.common.data.models import GrantRecipient
from app.common.data.types import RoleEnum, SubmissionEventType, SubmissionModeEnum


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

        # gr1 has submitted, so should not be in the list
        submission1 = factories.submission.create(
            grant_recipient=gr1,
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): "Blue"},
        )
        factories.submission_event.create(
            submission=submission1,
            related_entity_id=collection.forms[0].id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )
        factories.submission_event.create(submission=submission1, event_type=SubmissionEventType.SUBMISSION_SUBMITTED)

        # gr2 has sent for certification, not submitted, so should be in the list
        submission2 = factories.submission.create(
            grant_recipient=gr2,
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): "Blue"},
        )
        factories.submission_event.create(
            submission=submission2,
            related_entity_id=collection.forms[0].id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )
        factories.submission_event.create(
            submission=submission2, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )

        # gr3 has had their certification declined, so should be in the list
        submission3 = factories.submission.create(
            grant_recipient=gr3,
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): "Blue"},
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
        # org 4 has not started their report yet so should be in the list

        result = get_grant_recipients_with_outstanding_submissions_for_collection(
            grant, collection_id=collection.id, with_certifiers=True, with_data_providers=True
        )

        assert len(result) == 3
        assert {gr.organisation_id for gr in result} == {org2.id, org3.id, org4.id}


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

        create_grant_recipients(grant, [org1.id, org2.id, org3.id])

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 3
        assert {gr.organisation_id for gr in grant_recipients} == {org1.id, org2.id, org3.id}

    def test_creates_single_grant_recipient(self, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(name="Organisation 1")

        create_grant_recipients(grant, [org.id])

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 1
        assert grant_recipients[0].organisation_id == org.id
        assert grant_recipients[0].grant_id == grant.id

    def test_handles_empty_list(self, factories, db_session):
        grant = factories.grant.create()
        initial_count = db_session.query(GrantRecipient).count()

        create_grant_recipients(grant, [])

        db_session.expire_all()
        final_count = db_session.query(GrantRecipient).count()
        assert final_count == initial_count

    def test_adds_to_existing_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)

        create_grant_recipients(grant, [org2.id, org3.id])

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 3
        assert {gr.organisation_id for gr in grant_recipients} == {org1.id, org2.id, org3.id}


class TestGetGrantRecipientDataProvidersCount:
    def test_no_grant_recipient_users(self, db_session, factories):
        grant = factories.grant.create()

        count = get_grant_recipient_data_providers_count(grant)

        assert count == 0

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

        count = get_grant_recipient_data_providers_count(grant)

        assert count == 1

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

        count = get_grant_recipient_data_providers_count(grant)

        assert count == 3

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

        count = get_grant_recipient_data_providers_count(grant)

        assert count == 2

    def test_excludes_grant_team_members(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)

        grant_team_user = factories.user.create()
        factories.user_role.create(
            user=grant_team_user,
            organisation=grant.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        count = get_grant_recipient_data_providers_count(grant)

        assert count == 0

    def test_excludes_admin_roles(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])

        count = get_grant_recipient_data_providers_count(grant)

        assert count == 0

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

        count = get_grant_recipient_data_providers_count(grant1)

        assert count == 0


class TestAllGrantRecipientsHaveDataProviders:
    def test_returns_false_when_no_grant_recipients(self, db_session, factories):
        grant = factories.grant.create()

        result = all_grant_recipients_have_data_providers(grant)

        assert result is False

    def test_returns_false_when_grant_recipient_has_no_users(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)

        result = all_grant_recipients_have_data_providers(grant)

        assert result is False

    def test_returns_true_when_single_grant_recipient_has_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        result = all_grant_recipients_have_data_providers(grant)

        assert result is True

    def test_returns_true_when_all_grant_recipients_have_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        for grant_recipient in grant_recipients:
            user = factories.user.create()
            factories.user_role.create(
                user=user,
                organisation=grant_recipient.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            )

        result = all_grant_recipients_have_data_providers(grant)

        assert result is True

    def test_returns_false_when_some_grant_recipients_have_no_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipients[0].organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        result = all_grant_recipients_have_data_providers(grant)

        assert result is False

    def test_returns_true_when_grant_recipient_has_multiple_users(self, db_session, factories):
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

        result = all_grant_recipients_have_data_providers(grant)

        assert result is True

    def test_excludes_admin_roles(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])

        result = all_grant_recipients_have_data_providers(grant)

        assert result is False

    def test_excludes_users_from_different_grants(self, db_session, factories):
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

        result = all_grant_recipients_have_data_providers(grant1)

        assert result is False

    def test_excludes_grant_team_members(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        grant_team_user = factories.user.create()
        factories.user_role.create(
            user=grant_team_user,
            organisation=grant.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        result = all_grant_recipients_have_data_providers(grant)

        assert result is False


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
