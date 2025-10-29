from app.common.data.interfaces.grant_recipients import (
    create_grant_recipients,
    get_grant_recipients,
    get_grant_recipients_count,
)
from app.common.data.models import GrantRecipient


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
