import uuid

from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType


class TestCreateOrganisationSession:
    def test_to_session_dict_round_trips_through_json(self):
        collection_id = uuid.uuid4()
        session = CreateOrganisationSession(
            collection_id=collection_id,
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
        )

        session_dict = session.to_session_dict()

        assert session_dict["collection_id"] == str(collection_id)
        assert session_dict["organisation_type"] == "COMPANY"

        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored == session
        assert restored.collection_id == collection_id
        assert restored.organisation_type is SignUpOrganisationType.COMPANY

    def test_to_session_dict_excludes_none(self):
        session_dict = CreateOrganisationSession(collection_id=uuid.uuid4()).to_session_dict()

        assert "organisation_type" not in session_dict
        assert session_dict["name"] == ""
        assert session_dict["external_id"] == ""

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
