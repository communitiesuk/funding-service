import uuid

import pytest

from app.access_grant_funding.session_models import (
    CompleteCreateOrganisationSession,
    CreateOrganisationSession,
    NamedCreateOrganisationSession,
    SignUpOrganisationType,
)


def _session(collection_id, *, needs_user_name=False, can_share_email_domain=True, **answers):
    return CreateOrganisationSession(
        collection_id=collection_id,
        needs_user_name=needs_user_name,
        can_share_email_domain=can_share_email_domain,
        **answers,
    )


class TestCreateOrganisationSession:
    def test_start_records_the_steps_this_user_will_be_asked(self, factories):
        collection_id = uuid.uuid4()

        session = CreateOrganisationSession.start(
            collection_id=collection_id, user=factories.user.build(email="someone@no-org.com", name=None)
        )

        assert session.collection_id == collection_id
        assert session.needs_user_name is True
        assert session.can_share_email_domain is True

    def test_start_skips_the_steps_that_do_not_apply_to_this_user(self, factories):
        session = CreateOrganisationSession.start(
            collection_id=uuid.uuid4(), user=factories.user.build(email="someone@gmail.com", name="Test applicant")
        )

        assert session.needs_user_name is False
        assert session.can_share_email_domain is False

    def test_to_session_dict_round_trips_through_json(self):
        collection_id = uuid.uuid4()
        session = _session(
            collection_id,
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
            allow_team_members=True,
        )

        session_dict = session.to_session_dict()

        assert session_dict["collection_id"] == str(collection_id)
        assert session_dict["organisation_type"] == "COMPANY"
        assert session_dict["allow_team_members"] is True

        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored == session
        assert restored.collection_id == collection_id
        assert restored.organisation_type is SignUpOrganisationType.COMPANY
        assert restored.allow_team_members is True

    def test_to_session_dict_excludes_none(self):
        session_dict = _session(uuid.uuid4()).to_session_dict()

        assert "organisation_type" not in session_dict
        assert "allow_team_members" not in session_dict
        assert "name" not in session_dict
        assert "external_id" not in session_dict

    def test_companies_house_unavailable_defaults_to_false_and_round_trips(self):
        collection_id = uuid.uuid4()

        assert _session(collection_id).companies_house_unavailable is False

        session_dict = _session(collection_id, companies_house_unavailable=True).to_session_dict()
        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored.companies_house_unavailable is True

    def test_to_session_dict_keeps_allow_team_members_when_false(self):
        collection_id = uuid.uuid4()
        session_dict = _session(collection_id, allow_team_members=False).to_session_dict()

        assert session_dict["allow_team_members"] is False
        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored.allow_team_members is False

    def test_from_session_requires_matching_collection_id(self):
        session = _session(
            uuid.uuid4(),
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
        )
        assert (
            CreateOrganisationSession.from_session(collection_id=uuid.uuid4(), session_data=session.to_session_dict())
            is None
        )

    @pytest.mark.parametrize("unanswered", ["needs_user_name", "can_share_email_domain"])
    def test_from_session_needs_the_steps_this_user_is_asked_to_have_been_settled(self, unanswered):
        collection_id = uuid.uuid4()
        session_dict = _session(collection_id).to_session_dict()
        del session_dict[unanswered]

        assert CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict) is None


class TestNamedCreateOrganisationSession:
    def _session_dict(self, collection_id, **overrides):
        answers = {
            "organisation_type": SignUpOrganisationType.COMPANY,
            "name": "Acme Ltd",
            "external_id": "000123456",
        } | overrides
        return _session(collection_id, **answers).to_session_dict()

    def _load(self, session_dict, collection_id):
        return NamedCreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)

    def test_from_session_loads_a_session_that_has_named_the_organisation(self):
        collection_id = uuid.uuid4()

        loaded = self._load(self._session_dict(collection_id), collection_id)

        assert loaded is not None
        assert loaded.organisation_type is SignUpOrganisationType.COMPANY
        assert loaded.name == "Acme Ltd"
        assert loaded.external_id == "000123456"

    @pytest.mark.parametrize("unanswered", ["organisation_type", "name", "external_id"])
    def test_from_session_needs_the_organisation_type_name_and_id(self, unanswered):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id)
        del session_dict[unanswered]

        assert self._load(session_dict, collection_id) is None

    @pytest.mark.parametrize("left_blank", ["name", "external_id"])
    def test_from_session_does_not_take_a_blank_name_or_id_as_an_answer(self, left_blank):
        collection_id = uuid.uuid4()

        assert self._load(self._session_dict(collection_id, **{left_blank: ""}), collection_id) is None


class TestCompleteCreateOrganisationSession:
    def _session_dict(self, collection_id, **overrides):
        answers = {
            "organisation_type": SignUpOrganisationType.COMPANY,
            "name": "Acme Ltd",
            "external_id": "000123456",
            "allow_team_members": True,
        } | overrides
        return _session(collection_id, **answers).to_session_dict()

    def _load(self, session_dict, collection_id):
        return CompleteCreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)

    def test_from_session_loads_a_session_with_every_answer(self):
        collection_id = uuid.uuid4()

        loaded = self._load(self._session_dict(collection_id, needs_user_name=True, user_name="Test"), collection_id)

        assert loaded is not None
        assert loaded.name == "Acme Ltd"
        assert loaded.user_name == "Test"

    def test_from_session_does_not_need_a_full_name_when_the_step_was_skipped(self):
        collection_id = uuid.uuid4()

        assert self._load(self._session_dict(collection_id), collection_id) is not None

    def test_from_session_needs_a_full_name_when_the_user_was_asked_for_one(self):
        collection_id = uuid.uuid4()

        assert self._load(self._session_dict(collection_id, needs_user_name=True), collection_id) is None

    def test_from_session_needs_the_allow_team_members_answer(self):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id)
        del session_dict["allow_team_members"]

        assert self._load(session_dict, collection_id) is None

    def test_from_session_does_not_need_the_allow_team_members_answer_when_the_step_was_skipped(self):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id, can_share_email_domain=False)
        del session_dict["allow_team_members"]

        assert self._load(session_dict, collection_id) is not None
