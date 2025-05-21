import pytest
from sqlalchemy import func, select

from app.common.data import interfaces
from app.common.data.models import RoleEnum, User, UserRole


class TestGetUser:
    def test_get_user_by_id(self, db_session, factories):
        user_id = factories.user.create(email="test@communities.gov.uk").id

        user = interfaces.user.get_user(user_id)

        assert user.id == user_id
        assert user.email == "test@communities.gov.uk"


class TestGetOrCreateUser:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"

    def test_get_existing_user(self, db_session, factories):
        factories.user.create(email="test@communities.gov.uk")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"


class TestAddUserRole:
    @pytest.mark.parametrize(
        "organisation, grant, role",
        [
            (False, False, RoleEnum.ADMIN),
            (True, False, RoleEnum.MEMBER),
            (False, True, RoleEnum.ASSESSOR),
            (True, True, RoleEnum.EDITOR),
        ],
    )
    def test_add_user_role(self, db_session, factories, organisation, grant, role):
        # This test checks a few happy paths - the tests in test_constraints check against the table's constraints at
        # the DB level and additional tests will be added to check these errors are raised correctly once a custom
        # exception is created for this.
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        user_id = factories.user.create(email="test@communities.gov.uk").id
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        user_role = interfaces.user.add_user_role(
            user_id=user_id, organisation_id=organisation_id_value, grant_id=grant_id_value, role=role
        )

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1
        assert user_role.user_id == user_id
        assert (user_role.user_id, user_role.organisation_id, user_role.grant_id, user_role.role) == (
            user_id,
            organisation_id_value,
            grant_id_value,
            role,
        )

    def test_add_existing_user_role(self, db_session, factories):
        user_id = factories.user.create(email="test@communities.gov.uk").id
        interfaces.user.add_user_role(user_id=user_id, role=RoleEnum.ADMIN)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user.add_user_role(user_id=user_id, role=RoleEnum.ADMIN)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1
        assert user_role.user_id == user_id
        assert (user_role.organisation_id, user_role.grant_id) == (None, None)
        assert user_role.role == RoleEnum.ADMIN
