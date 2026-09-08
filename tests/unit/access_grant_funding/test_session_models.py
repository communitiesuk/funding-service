import uuid

import pytest

from app.access_grant_funding.session_models import (
    CompleteCreateOrganisationSession,
    CreateOrganisationSession,
    NamedCreateOrganisationSession,
    SignUpOrganisationType,
)


class TestCreateOrganisationSession:
    def test_to_session_dict_round_trips_through_json(self):
        collection_id = uuid.uuid4()
        session = CreateOrganisationSession(
            collection_id=collection_id,
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
        session_dict = CreateOrganisationSession(collection_id=uuid.uuid4()).to_session_dict()

        assert "organisation_type" not in session_dict
        assert "allow_team_members" not in session_dict
        assert "name" not in session_dict
        assert "external_id" not in session_dict

    def test_to_session_dict_keeps_allow_team_members_when_false(self):
        collection_id = uuid.uuid4()
        session_dict = CreateOrganisationSession(
            collection_id=collection_id, allow_team_members=False
        ).to_session_dict()

        assert session_dict["allow_team_members"] is False
        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored.allow_team_members is False

    def test_from_session_requires_matching_collection_id(self):
        collection_id = uuid.uuid4()
        session = CreateOrganisationSession(
            collection_id=collection_id,
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
        )
        assert (
            CreateOrganisationSession.from_session(collection_id=uuid.uuid4(), session_data=session.to_session_dict())
            is None
        )


class TestNamedCreateOrganisationSession:
    def _session_dict(self, collection_id, **overrides):
        answers = {
            "organisation_type": SignUpOrganisationType.COMPANY,
            "name": "Acme Ltd",
            "external_id": "000123456",
        } | overrides
        return CreateOrganisationSession(collection_id=collection_id, **answers).to_session_dict()

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
    def _session_dict(self, collection_id, **kwargs):
        return CreateOrganisationSession(
            collection_id=collection_id,
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
            allow_team_members=True,
            **kwargs,
        ).to_session_dict()

    def _load(self, session_dict, collection_id, user):
        return CompleteCreateOrganisationSession.from_session(
            collection_id=collection_id, session_data=session_dict, user=user
        )

    def test_from_session_loads_a_session_with_every_answer(self, factories):
        collection_id = uuid.uuid4()

        loaded = self._load(
            self._session_dict(collection_id), collection_id, factories.user.build(email="someone@no-org.com")
        )

        assert loaded is not None
        assert loaded.name == "Acme Ltd"
        assert loaded.organisation_type is SignUpOrganisationType.COMPANY

    def test_from_session_accepts_no_full_name_when_we_already_hold_one(self, factories):
        collection_id = uuid.uuid4()

        loaded = self._load(
            self._session_dict(collection_id),
            collection_id,
            factories.user.build(email="someone@no-org.com", name="Test applicant"),
        )

        assert loaded is not None

    def test_from_session_needs_a_full_name_when_we_hold_none(self, factories):
        collection_id = uuid.uuid4()

        assert (
            self._load(
                self._session_dict(collection_id),
                collection_id,
                factories.user.build(email="someone@no-org.com", name=None),
            )
            is None
        )

    def test_from_session_needs_the_allow_team_members_answer(self, factories):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id)
        del session_dict["allow_team_members"]

        assert self._load(session_dict, collection_id, factories.user.build(email="someone@no-org.com")) is None

    def test_from_session_skips_the_allow_team_members_answer_for_a_shared_email_domain(self, factories):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id)
        del session_dict["allow_team_members"]

        assert self._load(session_dict, collection_id, factories.user.build(email="someone@gmail.com")) is not None

    def test_from_session_without_a_user_cannot_tell_which_steps_were_skipped(self):
        collection_id = uuid.uuid4()

        with pytest.raises(TypeError):
            self._load(self._session_dict(collection_id), collection_id, None)
