import uuid
from datetime import datetime

import pytest
from flask_login import AnonymousUserMixin
from pytz import utc

from app import AuthorisationHelper, CollectionStatusEnum
from app.common.data.types import RoleEnum


class TestAuthorisationHelper:
    @pytest.mark.parametrize(
        "name, last_logged_in, expected",
        [
            ("John", datetime.now(utc), True),
            ("John", None, False),
            (None, datetime.now(utc), True),
            (None, None, False),
        ],
    )
    def test_has_logged_in(self, factories, name, last_logged_in, expected):
        user = factories.user.build(name=name, last_logged_in_at_utc=last_logged_in)
        assert AuthorisationHelper.has_logged_in(user) is expected

    @pytest.mark.parametrize(
        "role, has_grant_linked_to_role, expected",
        [
            (RoleEnum.ADMIN, False, True),
            (RoleEnum.ADMIN, True, False),
            (RoleEnum.MEMBER, True, False),
        ],
    )
    def test_is_platform_admin(self, factories, role, has_grant_linked_to_role, expected):
        user = factories.user.build()
        factories.user_role.build(user=user, permissions=[role], has_grant=has_grant_linked_to_role)
        assert AuthorisationHelper.is_platform_admin(user) is expected

    def test_is_platform_admin_works_for_anonymous_user(self):
        assert AuthorisationHelper.is_platform_admin(AnonymousUserMixin()) is False

    @pytest.mark.parametrize(
        "role, has_organisation_linked, can_manage_grants, expected",
        [
            (RoleEnum.ADMIN, True, True, True),
            (RoleEnum.ADMIN, True, False, False),
            (RoleEnum.MEMBER, True, True, False),
        ],
    )
    def test_is_deliver_org_admin(self, factories, role, has_organisation_linked, can_manage_grants, expected):
        user = factories.user.build()
        organisation = factories.organisation.build(can_manage_grants=can_manage_grants)
        factories.user_role.build(user=user, permissions=[role], organisation=organisation, grant=None)
        assert AuthorisationHelper.is_deliver_org_admin(user) is expected

    def test_is_deliver_org_admin_with_grant_id_set(self, factories):
        user = factories.user.build()
        organisation = factories.organisation.build(can_manage_grants=True)
        grant = factories.grant.build(organisation=organisation)
        factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN], organisation=organisation, grant=grant)
        assert AuthorisationHelper.is_deliver_org_admin(user) is False

    def test_is_deliver_org_admin_platform_admin_overrides(self, factories):
        user = factories.user.build()
        factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN], organisation=None, grant=None)
        assert AuthorisationHelper.is_deliver_org_admin(user) is True

    def test_is_deliver_org_admin_works_for_anonymous_user(self):
        assert AuthorisationHelper.is_deliver_org_admin(AnonymousUserMixin()) is False

    @pytest.mark.parametrize(
        "role, can_manage_grants, expected",
        [
            (RoleEnum.ADMIN, True, True),
            (RoleEnum.ADMIN, False, False),
            (RoleEnum.MEMBER, True, True),
        ],
    )
    def test_is_deliver_org_member(self, factories, role, can_manage_grants, expected):
        user = factories.user.build()
        organisation = factories.organisation.build(can_manage_grants=can_manage_grants)
        factories.user_role.build(user=user, permissions=[role], organisation=organisation, grant=None)
        assert AuthorisationHelper.is_deliver_org_member(user) is expected

    def test_is_deliver_org_member_with_grant_id_set(self, factories):
        user = factories.user.build()
        organisation = factories.organisation.build(can_manage_grants=True)
        grant = factories.grant.build(organisation=organisation)
        factories.user_role.build(user=user, permissions=[RoleEnum.MEMBER], organisation=organisation, grant=grant)
        assert AuthorisationHelper.is_deliver_org_member(user) is False

    def test_is_deliver_org_member_platform_admin_overrides(self, factories):
        user = factories.user.build()
        factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN], organisation=None, grant=None)
        assert AuthorisationHelper.is_deliver_org_member(user) is True

    def test_is_deliver_org_member_works_for_anonymous_user(self):
        assert AuthorisationHelper.is_deliver_org_member(AnonymousUserMixin()) is False

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, False),
        ],
    )
    def test_is_deliver_grant_admin_correct_grant(self, factories, role, expected, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)
        factories.user_role.build(user=user, permissions=[role], grant=grant)
        assert AuthorisationHelper.is_deliver_grant_admin(user=user, grant_id=grant.id) is expected

    @pytest.mark.parametrize(
        "role",
        [
            (RoleEnum.ADMIN),
            (RoleEnum.MEMBER),
        ],
    )
    def test_is_deliver_grant_admin_incorrect_grant(self, factories, role, mocker):
        user = factories.user.build()
        grant1 = factories.grant.build()
        grant2 = factories.grant.build()
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant2)
        factories.user_role.build(user=user, permissions=[role], grant=grant1)
        assert AuthorisationHelper.is_deliver_grant_admin(user=user, grant_id=grant2.id) is False

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, False),
        ],
    )
    def test_is_deliver_grant_admin_for_grant_roles(self, factories, role, expected, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, permissions=[role], grant=grant)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)
        assert AuthorisationHelper.is_deliver_grant_admin(user=user, grant_id=grant.id) is expected

    def test_is_deliver_grant_admin_if_platform_admin(self, factories, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)
        assert AuthorisationHelper.is_deliver_grant_admin(user=user, grant_id=grant.id) is False
        factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN])
        assert AuthorisationHelper.is_deliver_grant_admin(user=user, grant_id=grant.id) is True

    @pytest.mark.parametrize(
        "role",
        [
            RoleEnum.ADMIN,
            RoleEnum.MEMBER,
        ],
    )
    def test_is_deliver_grant_member_true(self, factories, role, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, permissions=[role], grant=grant)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)
        assert AuthorisationHelper.is_deliver_grant_member(user=user, grant_id=grant.id)

    @pytest.mark.parametrize("role", [RoleEnum.ADMIN, RoleEnum.MEMBER])
    def test_is_deliver_grant_member_false_member_of_different_grant(self, factories, role, mocker):
        user = factories.user.build()
        grants = factories.grant.build_batch(2)
        factories.user_role.build(user=user, permissions=[role], grant=grants[0])
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grants[1])
        assert AuthorisationHelper.is_deliver_grant_member(user=user, grant_id=grants[1].id) is False

    def test_is_deliver_grant_member_false_not_got_member_role(self, factories, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)
        assert AuthorisationHelper.is_deliver_grant_member(user=user, grant_id=grant.id) is False

    def test_is_deliver_grant_member_overriden_by_platform_admin(self, factories, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN], grant=None)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)
        assert AuthorisationHelper.is_deliver_grant_member(user=user, grant_id=grant.id) is True

    @pytest.mark.parametrize(
        "role, expected",
        [
            (RoleEnum.ADMIN, True),
            (RoleEnum.MEMBER, True),
            ("S151_OFFICER", pytest.raises(ValueError)),
        ],
    )
    def test_has_deliver_grant_role(self, factories, role, expected, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        factories.user_role.build(user=user, permissions=[role], grant=grant)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

        if isinstance(expected, bool):
            assert AuthorisationHelper.has_deliver_grant_role(user=user, grant_id=grant.id, role=role) is expected
        else:
            with expected:
                AuthorisationHelper.has_deliver_grant_role(user=user, grant_id=grant.id, role=role)

    @pytest.mark.parametrize(
        "collection_status",
        [status for status in CollectionStatusEnum if status != CollectionStatusEnum.DRAFT],
    )
    def test_can_edit_collection_returns_false_for_grant_admin_with_non_draft_collection(
        self, factories, mocker, collection_status
    ):
        user = factories.user.build()
        organisation = factories.organisation.build()
        grant = factories.grant.build(organisation=organisation)
        collection = factories.collection.build(grant=grant, status=collection_status)
        user_role = factories.user_role.build(
            user=user, permissions=[RoleEnum.ADMIN], grant=grant, organisation=organisation
        )
        user.roles = [user_role]

        mocker.patch("app.common.auth.authorisation_helper.get_collection", return_value=collection)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

        assert AuthorisationHelper.can_edit_collection(user=user, collection_id=collection.id) is False

    def test_can_edit_collection_returns_true_for_grant_admin_with_draft_collection(self, factories, mocker):
        user = factories.user.build()
        organisation = factories.organisation.build()
        grant = factories.grant.build(organisation=organisation)
        collection = factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)
        user_role = factories.user_role.build(
            user=user, permissions=[RoleEnum.ADMIN], grant=grant, organisation=organisation
        )
        user.roles = [user_role]

        mocker.patch("app.common.auth.authorisation_helper.get_collection", return_value=collection)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

        assert AuthorisationHelper.can_edit_collection(user=user, collection_id=collection.id) is True

    def test_can_edit_collection_returns_true_for_platform_admin_with_draft_collection(self, factories, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        collection = factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)
        user_role = factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN], grant=None)
        user.roles = [user_role]

        mocker.patch("app.common.auth.authorisation_helper.get_collection", return_value=collection)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

        assert AuthorisationHelper.can_edit_collection(user=user, collection_id=collection.id) is True

    def test_can_edit_collection_returns_false_for_platform_admin_with_non_draft_collection(self, factories, mocker):
        user = factories.user.build()
        grant = factories.grant.build()
        collection = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)
        user_role = factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN], grant=None)
        user.roles = [user_role]

        mocker.patch("app.common.auth.authorisation_helper.get_collection", return_value=collection)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

        assert AuthorisationHelper.can_edit_collection(user=user, collection_id=collection.id) is False

    def test_can_edit_collection_returns_false_for_anonymous_user(self, factories, mocker):
        collection = factories.collection.build(status=CollectionStatusEnum.DRAFT)
        mocker.patch("app.common.auth.authorisation_helper.get_collection", return_value=collection)

        assert AuthorisationHelper.can_edit_collection(user=AnonymousUserMixin(), collection_id=collection.id) is False

    def test_can_edit_collection_returns_false_for_grant_member(self, factories, mocker):
        user = factories.user.build()
        organisation = factories.organisation.build()
        grant = factories.grant.build(organisation=organisation)
        collection = factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)
        user_role = factories.user_role.build(
            user=user, permissions=[RoleEnum.MEMBER], grant=grant, organisation=organisation
        )
        user.roles = [user_role]

        mocker.patch("app.common.auth.authorisation_helper.get_collection", return_value=collection)
        mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

        assert AuthorisationHelper.can_edit_collection(user=user, collection_id=collection.id) is False

    def test_has_access_org_access_rejects_anonymous(self):
        assert (
            AuthorisationHelper.has_access_org_access(user=AnonymousUserMixin(), organisation_id=uuid.uuid4()) is False
        )

    def test_has_access_org_access(self, factories):
        user = factories.user.build()
        organisation = factories.organisation.build()
        non_member_organisation = factories.organisation.build()
        factories.user_role.build(user=user, permissions=[RoleEnum.MEMBER], organisation=organisation, grant=None)

        assert AuthorisationHelper.has_access_org_access(user=user, organisation_id=organisation.id) is True
        assert AuthorisationHelper.has_access_org_access(user=user, organisation_id=non_member_organisation.id) is False
