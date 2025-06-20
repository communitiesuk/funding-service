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


class TestGetUserByEmail:
    def test_get_existing_user(self, db_session, factories):
        factories.user.create(email="Test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_user_by_email(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "Test@communities.gov.uk"
        assert user.name == "My Name"

    def test_get_user_where_none_exists(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_user_by_email(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 0
        assert user is None


class TestGetUserByAzureAdSubjectId:
    def test_get_existing_user(self, db_session, factories):
        user = factories.user.create(email="Test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_user_by_azure_ad_subject_id(azure_ad_subject_id=user.azure_ad_subject_id)

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "Test@communities.gov.uk"
        assert user.name == "My Name"

    def test_get_user_where_none_exists(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_user_by_azure_ad_subject_id(azure_ad_subject_id="some_string_value")

        assert db_session.scalar(select(func.count()).select_from(User)) == 0
        assert user is None


class TestUpsertUserByEmail:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.upsert_user_by_email(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"
        assert user.name is None and user.azure_ad_subject_id is None

    def test_get_existing_user_with_update(self, db_session, factories):
        factories.user.create(email="test@communities.gov.uk", name="My Name", azure_ad_subject_id=None)
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.upsert_user_by_email(email_address="test@communities.gov.uk", name="My Name updated")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"
        assert user.name == "My Name updated"
        assert user.azure_ad_subject_id is None


class TestUpsertUserByAzureAdSubjectId:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id="some_example_string", email_address="test@communities.gov.uk"
        )

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"
        assert user.azure_ad_subject_id == "some_example_string"
        assert user.name is None

    def test_get_existing_user_with_update(self, db_session, factories):
        factory_user = factories.user.create(email="test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id=factory_user.azure_ad_subject_id,
            email_address="updated@communities.gov.uk",
            name="My Name updated",
        )

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "updated@communities.gov.uk"
        assert user.name == "My Name updated"


class TestUpsertUserRole:
    @pytest.mark.parametrize(
        "organisation, grant, role",
        [
            (False, False, RoleEnum.ADMIN),
            (True, False, RoleEnum.MEMBER),
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

        user_role = interfaces.user.upsert_user_role(
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

    def test_multiple_roles_treated_as_distinct_and_dont_overwrite(self, db_session, factories):
        # Make sure that the handling of nulls on the constraint, and the upsert behaviour of `upsert_user_role`
        # will definitely create new roles on any mismatch between user_id/organisation_id/grant_id.
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        user = factories.user.create(email="test@communities.gov.uk")
        organisation = factories.organisation.create()
        grant = factories.grant.create()

        interfaces.user.upsert_user_role(
            user_id=user.id, organisation_id=organisation.id, grant_id=grant.id, role=RoleEnum.MEMBER
        )
        interfaces.user.upsert_user_role(
            user_id=user.id, organisation_id=organisation.id, grant_id=None, role=RoleEnum.MEMBER
        )
        interfaces.user.upsert_user_role(user_id=user.id, organisation_id=None, grant_id=grant.id, role=RoleEnum.ADMIN)
        interfaces.user.upsert_user_role(user_id=user.id, organisation_id=None, grant_id=None, role=RoleEnum.ADMIN)

        user_roles = db_session.query(UserRole).all()
        assert {(ur.user_id, ur.organisation_id, ur.grant_id, ur.role) for ur in user_roles} == {
            (user.id, organisation.id, grant.id, RoleEnum.MEMBER),
            (user.id, organisation.id, None, RoleEnum.MEMBER),
            (user.id, None, grant.id, RoleEnum.ADMIN),
            (user.id, None, None, RoleEnum.ADMIN),
        }

    def test_add_existing_user_role(self, db_session, factories):
        user_id = factories.user.create(email="test@communities.gov.uk").id
        interfaces.user.upsert_user_role(user_id=user_id, role=RoleEnum.ADMIN)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user.upsert_user_role(user_id=user_id, role=RoleEnum.ADMIN)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1
        assert user_role.user_id == user_id
        assert (user_role.organisation_id, user_role.grant_id) == (None, None)
        assert user_role.role == RoleEnum.ADMIN

    def test_upsert_existing_user_role(self, db_session, factories):
        user_id = factories.user.create(email="test@communities.gov.uk").id
        grant = factories.grant.create()
        interfaces.user.upsert_user_role(user_id=user_id, grant_id=grant.id, role=RoleEnum.MEMBER)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user.upsert_user_role(user_id=user_id, grant_id=grant.id, role=RoleEnum.ADMIN)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1
        assert user_role.user_id == user_id
        assert (user_role.organisation_id, user_role.grant_id) == (None, grant.id)
        assert user_role.role == RoleEnum.ADMIN

    @pytest.mark.parametrize(
        "organisation, grant, role, message",
        [
            (False, False, RoleEnum.MEMBER, "A 'member' role must be linked to an organisation or grant."),
        ],
    )
    def test_add_invalid_user_role(self, factories, organisation, grant, role, message):
        user_id = factories.user.create(email="test@communities.gov.uk").id
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        with pytest.raises(InvalidUserRoleError) as error:
            interfaces.user.upsert_user_role(
                user_id=user_id,
                organisation_id=organisation_id_value,
                grant_id=grant_id_value,
                role=role,
            )
        assert isinstance(error.value, InvalidUserRoleError)
        assert error.value.message == message
