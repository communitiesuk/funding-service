import pytest
from sqlalchemy import func, select

from app.common.data import interfaces
from app.common.data.interfaces.exceptions import InvalidUserRoleError
from app.common.data.models_user import User, UserRole
from app.common.data.types import RoleEnum


class TestGetUser:
    def test_get_user_by_id(self, db_session, factories):
        user_id = factories.user.create(email="test@communities.gov.uk").id

        user = interfaces.user.get_user(user_id)

        assert user.id == user_id
        assert user.email == "test@communities.gov.uk"

    def test_get_platform_admin_users(self, db_session, factories):
        users = factories.user.create_batch(5)
        for user in users:
            factories.user_role.create(user=user, role=RoleEnum.ADMIN)
        user = factories.user.create()
        grant = factories.grant.create()
        factories.user_role.create(user=user, role=RoleEnum.MEMBER, grant=grant)
        admin_users = interfaces.user.get_platform_admin_users()
        assert len(admin_users) == len(users)
        for admin in admin_users:
            assert RoleEnum.ADMIN in [role.role for role in admin.roles]


class GetUserByEmail:
    def test_get_existing_user(self, db_session, factories):
        factories.user.create(email="Test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_user_by_email(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "Test@communities.gov.uk"
        assert user.name == "My Name"


class TestGetOrCreateUser:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"

    def test_get_existing_user_with_update(self, db_session, factories):
        factories.user.create(email="test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk", name="My Name updated")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"
        assert user.name == "My Name updated"

    def test_get_existing_user_can_set_name(self, db_session, factories):
        factories.user.create(email="test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk", name="My NewName")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"
        assert user.name == "My NewName"


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

    @pytest.mark.parametrize(
        "organisation, grant, role, message",
        [
            (False, False, RoleEnum.MEMBER, "A 'member' role must be linked to an organisation or grant."),
            (True, False, RoleEnum.ASSESSOR, "An 'assessor' role can only be linked to a grant."),
            (False, True, RoleEnum.S151_OFFICER, "A 's151_officer' role can only be linked to an organisation."),
        ],
    )
    def test_add_invalid_user_role(self, factories, organisation, grant, role, message):
        user_id = factories.user.create(email="test@communities.gov.uk").id
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        with pytest.raises(InvalidUserRoleError) as error:
            interfaces.user.add_user_role(
                user_id=user_id,
                organisation_id=organisation_id_value,
                grant_id=grant_id_value,
                role=role,
            )
        assert isinstance(error.value, InvalidUserRoleError)
        assert error.value.message == message
