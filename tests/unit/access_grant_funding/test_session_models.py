import uuid

import pytest
from pydantic import ValidationError

from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType
from app.common.data.types import OrganisationType


class TestSignUpOrganisationType:
    @pytest.mark.parametrize(
        "sign_up_type, expected",
        [
            (SignUpOrganisationType.COMPANY, OrganisationType.COMPANY),
            (SignUpOrganisationType.CHARITY, OrganisationType.CHARITY),
            (SignUpOrganisationType.OTHER, OrganisationType.OTHER),
            (SignUpOrganisationType.LOCAL_AUTHORITY, None),
        ],
    )
    def test_organisation_type_mapping(self, sign_up_type, expected):
        assert sign_up_type.organisation_type == expected

    @pytest.mark.parametrize(
        "sign_up_type, expected_label",
        [
            (SignUpOrganisationType.COMPANY, "Registered company"),
            (SignUpOrganisationType.CHARITY, "Charity"),
            (SignUpOrganisationType.LOCAL_AUTHORITY, "Local authority"),
            (SignUpOrganisationType.OTHER, "Other"),
        ],
    )
    def test_label(self, sign_up_type, expected_label):
        assert sign_up_type.label == expected_label


class TestCreateOrganisationSession:
    def test_to_session_dict_round_trips_through_json(self):
        collection_id = uuid.uuid4()
        session = CreateOrganisationSession(
            collection_id=collection_id,
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            custom_code="000123456",
        )

        session_dict = session.to_session_dict()

        # The UUID in particular must be JSON-serialisable so it is not put into the signed cookie as a UUID object
        assert session_dict["collection_id"] == str(collection_id)
        assert session_dict["organisation_type"] == "COMPANY"

        restored = CreateOrganisationSession.from_session(session_dict)
        assert restored == session
        assert restored.collection_id == collection_id
        assert restored.organisation_type is SignUpOrganisationType.COMPANY

    def test_to_session_dict_excludes_none(self):
        session_dict = CreateOrganisationSession(collection_id=uuid.uuid4()).to_session_dict()

        assert "organisation_type" not in session_dict
        assert session_dict["name"] == ""
        assert session_dict["custom_code"] == ""

    def test_from_session_requires_collection_id(self):
        with pytest.raises(ValidationError):
            CreateOrganisationSession.from_session({})
