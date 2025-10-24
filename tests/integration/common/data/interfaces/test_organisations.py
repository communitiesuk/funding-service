from app.common.data.interfaces.organisations import get_organisation_count


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
