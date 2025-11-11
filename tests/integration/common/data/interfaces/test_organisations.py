import datetime

from app.common.data.interfaces.organisations import get_organisation_count, get_organisations, upsert_organisations
from app.common.data.models import Organisation
from app.common.data.types import OrganisationData, OrganisationStatus, OrganisationType


class TestGetOrganisations:
    def test_returns_grant_managing_organisations(self, factories, db_session):
        from tests.models import _get_grant_managing_organisation

        grant_managing_org = _get_grant_managing_organisation()
        factories.organisation.create(name="Regular Org 1", can_manage_grants=False)
        factories.organisation.create(name="Regular Org 2", can_manage_grants=False)

        result = get_organisations(can_manage_grants=True)

        assert len(result) == 1
        assert result[0].id == grant_managing_org.id

    def test_returns_non_grant_managing_organisations(self, factories, db_session):
        from tests.models import _get_grant_managing_organisation

        _get_grant_managing_organisation()
        org1 = factories.organisation.create(name="Regular Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Regular Org 2", can_manage_grants=False)
        org3 = factories.organisation.create(name="Regular Org 3", can_manage_grants=False)

        result = get_organisations(can_manage_grants=False)

        assert len(result) == 3
        assert {org.id for org in result} == {org1.id, org2.id, org3.id}

    def test_returns_empty_list_when_no_matches(self, factories, db_session):
        from tests.models import _get_grant_managing_organisation

        _get_grant_managing_organisation()

        result = get_organisations(can_manage_grants=False)

        assert result == []

    def test_returns_all_organisations_when_can_manage_grants_is_none(self, factories, db_session):
        from tests.models import _get_grant_managing_organisation

        grant_managing_org = _get_grant_managing_organisation()
        org1 = factories.organisation.create(name="Regular Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Regular Org 2", can_manage_grants=False)

        result = get_organisations(can_manage_grants=None)

        assert len(result) == 3
        assert {org.id for org in result} == {grant_managing_org.id, org1.id, org2.id}


class TestGetOrganisationCount:
    def test_returns_count_of_non_grant_managing_organisations(self, factories, db_session):
        factories.organisation.create(name="Regular Org 1", can_manage_grants=False)
        factories.organisation.create(name="Regular Org 2", can_manage_grants=False)
        factories.organisation.create(name="Regular Org 3", can_manage_grants=False)

        assert get_organisation_count() == 3

    def test_counts_only_non_grant_managing_organisations(self, factories, db_session):
        from tests.models import _get_grant_managing_organisation

        _get_grant_managing_organisation()
        factories.organisation.create(name="Regular Org 1", can_manage_grants=False)
        factories.organisation.create(name="Regular Org 2", can_manage_grants=False)

        assert get_organisation_count() == 2


class TestUpsertOrganisations:
    def test_inserts_new_organisation(self, db_session):
        new_org = OrganisationData(
            external_id="GB-GOV-123",
            name="Test Department",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=datetime.date(2020, 1, 1),
            retirement_date=None,
        )

        upsert_organisations([new_org])

        db_session.expire_all()
        org_from_db = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org_from_db.name == "Test Department"
        assert org_from_db.type == OrganisationType.CENTRAL_GOVERNMENT
        assert org_from_db.can_manage_grants is False
        assert org_from_db.status == OrganisationStatus.ACTIVE
        assert org_from_db.active_date == datetime.date(2020, 1, 1)
        assert org_from_db.retirement_date is None

    def test_inserts_multiple_new_organisations(self, db_session):
        orgs = [
            OrganisationData(
                external_id="GB-GOV-123",
                name="Department A",
                type=OrganisationType.CENTRAL_GOVERNMENT,
                active_date=None,
                retirement_date=None,
            ),
            OrganisationData(
                external_id="E06000001",
                name="Council A",
                type=OrganisationType.UNITARY_AUTHORITY,
                active_date=None,
                retirement_date=None,
            ),
            OrganisationData(
                external_id="E07000001",
                name="Council B",
                type=OrganisationType.SHIRE_DISTRICT,
                active_date=None,
                retirement_date=None,
            ),
        ]

        upsert_organisations(orgs)

        db_session.expire_all()
        assert db_session.query(Organisation).filter_by(external_id="GB-GOV-123").count() == 1
        assert db_session.query(Organisation).filter_by(external_id="E06000001").count() == 1
        assert db_session.query(Organisation).filter_by(external_id="E07000001").count() == 1

    def test_updates_existing_organisation_by_external_id(self, factories, db_session):
        existing_org = factories.organisation.create(
            external_id="GB-GOV-123",
            name="Old Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            can_manage_grants=False,
        )

        updated_org = OrganisationData(
            external_id="GB-GOV-123",
            name="New Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=datetime.date(2021, 5, 15),
            retirement_date=None,
        )

        upsert_organisations([updated_org])

        db_session.expire_all()
        org_from_db = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org_from_db.id == existing_org.id
        assert org_from_db.name == "New Name"
        assert org_from_db.active_date == datetime.date(2021, 5, 15)

    def test_sets_status_to_active_when_no_retirement_date(self, db_session):
        org = OrganisationData(
            external_id="GB-GOV-123",
            name="Active Org",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=None,
            retirement_date=None,
        )

        upsert_organisations([org])

        db_session.expire_all()
        org_from_db = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org_from_db.status == OrganisationStatus.ACTIVE

    def test_sets_status_to_retired_when_retirement_date_present(self, db_session):
        org = OrganisationData(
            external_id="GB-GOV-123",
            name="Retired Org",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=datetime.date(2010, 1, 1),
            retirement_date=datetime.date(2020, 12, 31),
        )

        upsert_organisations([org])

        db_session.expire_all()
        org_from_db = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org_from_db.status == OrganisationStatus.RETIRED
        assert org_from_db.retirement_date == datetime.date(2020, 12, 31)

    def test_updates_organisation_status_from_active_to_retired(self, factories, db_session, caplog):
        existing_org = factories.organisation.create(
            external_id="GB-GOV-123",
            name="Org Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            status=OrganisationStatus.ACTIVE,
            can_manage_grants=False,
            retirement_date=None,
        )

        updated_org = OrganisationData(
            external_id="GB-GOV-123",
            name="Org Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=None,
            retirement_date=datetime.date(2023, 6, 30),
        )

        upsert_organisations([updated_org])

        db_session.expire_all()
        org_from_db = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org_from_db.id == existing_org.id
        assert org_from_db.status == OrganisationStatus.RETIRED
        assert org_from_db.retirement_date == datetime.date(2023, 6, 30)

        assert len(caplog.messages) == 1
        assert "Active organisation Org Name [GB-GOV-123] has been retired as of 2023-06-30" in caplog.messages[0]

    def test_updates_organisation_status_from_retired_to_active(self, factories, db_session):
        existing_org = factories.organisation.create(
            external_id="GB-GOV-123",
            name="Org Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            status=OrganisationStatus.RETIRED,
            can_manage_grants=False,
            retirement_date=datetime.date(2020, 12, 31),
        )

        updated_org = OrganisationData(
            external_id="GB-GOV-123",
            name="Org Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=None,
            retirement_date=None,
        )

        upsert_organisations([updated_org])

        db_session.expire_all()
        org_from_db = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org_from_db.id == existing_org.id
        assert org_from_db.status == OrganisationStatus.ACTIVE
        assert org_from_db.retirement_date is None

    def test_upserts_mix_of_new_and_existing_organisations(self, factories, db_session):
        factories.organisation.create(
            external_id="GB-GOV-123",
            name="Existing Org",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            can_manage_grants=False,
        )

        orgs = [
            OrganisationData(
                external_id="GB-GOV-123",
                name="Updated Existing Org",
                type=OrganisationType.CENTRAL_GOVERNMENT,
                active_date=None,
                retirement_date=None,
            ),
            OrganisationData(
                external_id="E06000001",
                name="New Org",
                type=OrganisationType.UNITARY_AUTHORITY,
                active_date=None,
                retirement_date=None,
            ),
        ]

        upsert_organisations(orgs)

        db_session.expire_all()
        existing_org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert existing_org.name == "Updated Existing Org"

        new_org = db_session.query(Organisation).filter_by(external_id="E06000001").one()
        assert new_org.name == "New Org"

    def test_logs_multiple_organisations_retired(self, factories, db_session, caplog):
        factories.organisation.create(
            external_id="GB-GOV-123",
            name="Department A",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            status=OrganisationStatus.ACTIVE,
            can_manage_grants=False,
        )
        factories.organisation.create(
            external_id="E06000001",
            name="Council B",
            type=OrganisationType.UNITARY_AUTHORITY,
            status=OrganisationStatus.ACTIVE,
            can_manage_grants=False,
        )

        updated_orgs = [
            OrganisationData(
                external_id="GB-GOV-123",
                name="Department A",
                type=OrganisationType.CENTRAL_GOVERNMENT,
                active_date=None,
                retirement_date=datetime.date(2023, 6, 30),
            ),
            OrganisationData(
                external_id="E06000001",
                name="Council B",
                type=OrganisationType.UNITARY_AUTHORITY,
                active_date=None,
                retirement_date=datetime.date(2023, 12, 31),
            ),
        ]

        upsert_organisations(updated_orgs)

        db_session.expire_all()
        assert len(caplog.messages) == 2
        assert "Active organisation Department A [GB-GOV-123] has been retired as of 2023-06-30" in caplog.messages
        assert "Active organisation Council B [E06000001] has been retired as of 2023-12-31" in caplog.messages

    def test_does_not_log_when_inserting_new_retired_organisation(self, db_session, caplog):
        new_org = OrganisationData(
            external_id="GB-GOV-123",
            name="Already Retired Org",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=None,
            retirement_date=datetime.date(2020, 12, 31),
        )

        upsert_organisations([new_org])

        db_session.expire_all()
        assert len(caplog.messages) == 0

    def test_does_not_log_when_active_organisation_remains_active(self, factories, db_session, caplog):
        factories.organisation.create(
            external_id="GB-GOV-123",
            name="Old Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            status=OrganisationStatus.ACTIVE,
            can_manage_grants=False,
        )

        updated_org = OrganisationData(
            external_id="GB-GOV-123",
            name="New Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=None,
            retirement_date=None,
        )

        upsert_organisations([updated_org])

        db_session.expire_all()
        assert len(caplog.messages) == 0

    def test_does_not_log_when_retired_organisation_becomes_active(self, factories, db_session, caplog):
        factories.organisation.create(
            external_id="GB-GOV-123",
            name="Org Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            status=OrganisationStatus.RETIRED,
            can_manage_grants=False,
            retirement_date=datetime.date(2020, 12, 31),
        )

        updated_org = OrganisationData(
            external_id="GB-GOV-123",
            name="Org Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            active_date=None,
            retirement_date=None,
        )

        upsert_organisations([updated_org])

        db_session.expire_all()
        assert len(caplog.messages) == 0

    def test_handles_empty_list(self, db_session):
        initial_count = db_session.query(Organisation).count()

        upsert_organisations([])

        db_session.expire_all()
        final_count = db_session.query(Organisation).count()
        assert final_count == initial_count
