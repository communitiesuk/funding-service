import uuid
from uuid import UUID

import pytest
from flask import session, url_for
from flask_login import login_user
from sqlalchemy.exc import NoResultFound
from werkzeug.exceptions import Forbidden, InternalServerError

from app.common.auth.decorators import (
    access_grant_funding_login_required,
    collection_is_editable,
    deliver_grant_funding_login_required,
    has_deliver_grant_role,
    is_access_org_member,
    is_deliver_grant_funding_user,
    is_deliver_org_admin,
    is_deliver_org_member,
    is_platform_admin,
    redirect_if_authenticated,
)
from app.common.data import interfaces
from app.common.data.types import AuthMethodEnum, CollectionStatusEnum, RoleEnum


class TestDeliverGrantFundingLoginRequired:
    def test_logged_in_user_gets_response(self, app, factories):
        @deliver_grant_funding_login_required
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk", azure_ad_subject_id=None)

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO
        response = test_deliver_grant_funding_login_required()
        assert response == "OK"

    def test_anonymous_user_gets_redirect(self, app):
        @deliver_grant_funding_login_required
        def test_deliver_grant_funding_login_required():
            return "OK"

        response = test_deliver_grant_funding_login_required()
        assert response.status_code == 302
        assert response.location == url_for("auth.sso_sign_in")

    def test_no_session_auth_variable(self, factories, app) -> None:
        @deliver_grant_funding_login_required
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@anything.com", azure_ad_subject_id=None)

        login_user(user)
        with pytest.raises(InternalServerError):
            test_deliver_grant_funding_login_required()


class TestAccessGrantFundingLoginRequired:
    def test_logged_in_user_gets_response(self, app, factories):
        @access_grant_funding_login_required
        def test_access_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@example.com", azure_ad_subject_id=None)

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK
        response = test_access_grant_funding_login_required()
        assert response == "OK"

    def test_anonymous_user_gets_redirect(self, app):
        @access_grant_funding_login_required
        def test_access_grant_funding_login_required():
            return "OK"

        response = test_access_grant_funding_login_required()
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    def test_no_session_auth_variable(self, factories, app) -> None:
        @access_grant_funding_login_required
        def test_access_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@anything.com", azure_ad_subject_id=None)

        login_user(user)
        with pytest.raises(InternalServerError):
            test_access_grant_funding_login_required()


class TestMHCLGLoginRequired:
    def test_logged_in_mhclg_user_gets_response(self, app, factories):
        @is_deliver_grant_funding_user
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO
        response = test_deliver_grant_funding_login_required()
        assert response == "OK"

    def test_non_mhclg_user_is_forbidden(self, app, factories):
        @is_deliver_grant_funding_user
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@anything.com")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.MAGIC_LINK
            test_deliver_grant_funding_login_required()

    def test_anonymous_user_gets_redirect(self, app):
        @is_deliver_grant_funding_user
        def test_deliver_grant_funding_login_required():
            return "OK"

        response = test_deliver_grant_funding_login_required()
        assert response.status_code == 302

    def test_deliver_grant_funding_user_auth_via_magic_link(self, app, factories) -> None:
        @is_deliver_grant_funding_user
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.ADMIN])

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK
        response = test_deliver_grant_funding_login_required()
        current_user = interfaces.user.get_current_user()
        assert response.status_code == 302
        assert current_user.is_anonymous is True

    def test_authed_via_magic_link_not_sso(self, app, factories) -> None:
        @is_deliver_grant_funding_user
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.MAGIC_LINK
            test_deliver_grant_funding_login_required()


class TestPlatformAdminRoleRequired:
    def test_logged_in_platform_admin_gets_response(self, app, factories):
        @is_platform_admin
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.ADMIN])

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = test_deliver_grant_funding_login_required()
        assert response == "OK"

    def test_non_platform_admin_is_forbidden(self, app, factories):
        @is_platform_admin
        def test_deliver_grant_funding_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_grant_funding_login_required()

    def test_anonymous_user_gets_redirect(self, app):
        @is_platform_admin
        def test_deliver_grant_funding_login_required():
            return "OK"

        response = test_deliver_grant_funding_login_required()
        assert response.status_code == 302


class TestDeliverOrgAdminRoleRequired:
    def test_logged_in_deliver_org_admin_gets_response(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(
            user_id=user.id, user=user, permissions=[RoleEnum.ADMIN], organisation=grant.organisation
        )

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = test_deliver_org_admin_required()
        assert response == "OK"

    def test_platform_admin_gets_response(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.ADMIN])

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = test_deliver_org_admin_required()
        assert response == "OK"

    def test_non_deliver_org_admin_is_forbidden(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_admin_required()

    def test_org_admin_without_can_manage_grants_is_forbidden(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        organisation = factories.organisation.create(can_manage_grants=False)
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.ADMIN], organisation=organisation)

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_admin_required()

    def test_grant_admin_is_forbidden(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_admin_required()

    def test_member_role_is_forbidden(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(
            user_id=user.id, user=user, permissions=[RoleEnum.MEMBER], organisation=grant.organisation
        )

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_admin_required()

    def test_anonymous_user_gets_redirect(self, app):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        response = test_deliver_org_admin_required()
        assert response.status_code == 302

    def test_deliver_org_admin_user_auth_via_magic_link(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(
            user_id=user.id, user=user, permissions=[RoleEnum.ADMIN], organisation=grant.organisation
        )

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK
        response = test_deliver_org_admin_required()
        current_user = interfaces.user.get_current_user()
        assert response.status_code == 302
        assert current_user.is_anonymous is True

    def test_authed_via_magic_link_not_sso(self, app, factories):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.MAGIC_LINK
            test_deliver_org_admin_required()


class TestDeliverOrgMemberRoleRequired:
    def test_logged_in_deliver_org_member_gets_response(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(
            user_id=user.id, user=user, permissions=[RoleEnum.MEMBER], organisation=grant.organisation
        )

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = test_deliver_org_member_required()
        assert response == "OK"

    def test_platform_admin_gets_response(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.ADMIN])

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = test_deliver_org_member_required()
        assert response == "OK"

    def test_non_deliver_org_member_is_forbidden(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_member_required()

    def test_org_member_without_can_manage_grants_is_forbidden(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        organisation = factories.organisation.create(can_manage_grants=False)
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.MEMBER], organisation=organisation)

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_member_required()

    def test_grant_member_is_forbidden(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.MEMBER], grant=grant)

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.SSO
            test_deliver_org_member_required()

    def test_anonymous_user_gets_redirect(self, app):
        @is_deliver_org_admin
        def test_deliver_org_admin_required():
            return "OK"

        response = test_deliver_org_admin_required()
        assert response.status_code == 302

    def test_deliver_org_member_user_auth_via_magic_link(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(
            user_id=user.id, user=user, permissions=[RoleEnum.MEMBER], organisation=grant.organisation
        )

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK
        response = test_deliver_org_member_required()
        current_user = interfaces.user.get_current_user()
        assert response.status_code == 302
        assert current_user.is_anonymous is True

    def test_authed_via_magic_link_not_sso(self, app, factories):
        @is_deliver_org_member
        def test_deliver_org_member_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            session["auth"] = AuthMethodEnum.MAGIC_LINK
            test_deliver_org_member_required()


class TestRedirectIfAuthenticated:
    def test_authenticated_user_gets_redirect(self, app, factories):
        @redirect_if_authenticated
        def test_authenticated_redirect():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = test_authenticated_redirect()
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.list_grants")

    def test_external_authenticated_user_gets_redirected(self, app, factories):
        @redirect_if_authenticated
        def test_authenticated_redirect():
            return "OK"

        user = factories.user.create(email="test@anything.com")

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO
        response = test_authenticated_redirect()
        assert response.status_code == 302
        assert response.location == url_for("developers.access.grants_list")

    def test_anonymous_user_gets_response(self, app):
        @redirect_if_authenticated
        def test_authenticated_redirect():
            return "OK"

        response = test_authenticated_redirect()
        assert response == "OK"


class TestHasDeliverGrantRole:
    def test_user_no_roles(self, factories):
        user = factories.user.create(email="test.norole@communities.gov.uk")
        grant = factories.grant.create()

        @has_deliver_grant_role(role=RoleEnum.ADMIN)
        def view_func(grant_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO
        with pytest.raises(Forbidden) as exc_info:
            view_func(grant_id=grant.id)

        assert "Access denied" in str(exc_info.value)

    def test_admin_user_has_access(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])

        @has_deliver_grant_role(role=RoleEnum.ADMIN)
        def view_func(grant_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(grant_id="abc")
        assert response == "OK"

    def test_no_result_on_non_existent_grant(self, factories):
        user = factories.user.create(email="test.member2@communities.gov.uk")

        @has_deliver_grant_role(role=RoleEnum.ADMIN)
        def view_func(grant_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        with pytest.raises(NoResultFound):
            view_func(grant_id=uuid.uuid4())

    def test_without_grant_id(self, factories):
        user = factories.user.create(email="test.member2@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)

        @has_deliver_grant_role(role=RoleEnum.ADMIN)
        def view_func(grant_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO
        with pytest.raises(ValueError, match="Grant ID required"):
            view_func(grant_id=None)

    def test_member_user_has_access(self, factories):
        user = factories.user.create(email="test.member@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)

        @has_deliver_grant_role(role=RoleEnum.MEMBER)
        def view_func(grant_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(grant_id=grant.id)
        assert response == "OK"

    def test_member_user_denied_for_admin_role(self, factories):
        user = factories.user.create(email="test.member2@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)

        @has_deliver_grant_role(role=RoleEnum.ADMIN)
        def view_func(grant_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        with pytest.raises(Forbidden) as e:
            view_func(grant_id=grant.id)
        assert "Access denied" in str(e.value)


class TestCollectionIsEditable:
    def test_grant_admin_can_access_draft_collection(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(collection_id=collection.id)
        assert response == "OK"

    @pytest.mark.parametrize(
        "collection_status",
        [status for status in CollectionStatusEnum if status != CollectionStatusEnum.DRAFT],
    )
    def test_grant_admin_redirected_for_non_draft_collection(self, factories, collection_status):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=collection_status)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(collection_id=collection.id)
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.list_reports", grant_id=grant.id)

    def test_platform_admin_can_access_draft_collection(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=None)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(collection_id=collection.id)
        assert response == "OK"

    def test_platform_admin_redirected_for_non_draft_collection(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.OPEN)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=None)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(collection_id=collection.id)
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.list_reports", grant_id=grant.id)

    def test_member_forbidden(self, factories):
        user = factories.user.create(email="test.member@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(collection_id=collection.id)
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.list_reports", grant_id=grant.id)

    def test_anonymous_user_gets_redirect(self, app, factories):
        collection = factories.collection.create(status=CollectionStatusEnum.DRAFT)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        response = view_func(collection_id=collection.id)
        assert response.status_code == 302

    def test_magic_link_auth_forbidden(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK

        response = view_func(collection_id=collection.id)
        assert response.status_code == 302
        assert response.location == url_for("auth.sso_sign_in")

    def test_redirects_to_correct_unauthorised_endpoint(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.OPEN)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        @collection_is_editable()
        def view_func(collection_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(collection_id=collection.id)
        assert response.status_code == 302
        assert response.location == url_for("deliver_grant_funding.list_reports", grant_id=grant.id)

    def test_with_form_id_parameter(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        form = factories.form.create(collection=collection)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        @collection_is_editable()
        def view_func(form_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(form_id=form.id)
        assert response == "OK"

    def test_with_component_id_parameter(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN], grant=grant)

        @collection_is_editable()
        def view_func(component_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.SSO

        response = view_func(component_id=question.id)
        assert response == "OK"


class TestIsAccessOrgMember:
    def test_user_missing_params(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")

        @is_access_org_member
        def view_func():
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK

        with pytest.raises(ValueError, match="Organisation ID required."):
            view_func()

    def test_user_non_org_member_rejected(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)

        @is_access_org_member
        def view_func(organisation_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK

        with pytest.raises(Forbidden):
            view_func(organisation_id=grant_recipient.organisation.id)

    def test_user_org_member_responds(self, factories):
        user = factories.user.create(email="test.admin@communities.gov.uk")
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        factories.user_role.create(
            user=user,
            permissions=[RoleEnum.MEMBER],
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
        )

        @is_access_org_member
        def view_func(organisation_id: UUID):
            return "OK"

        login_user(user)
        session["auth"] = AuthMethodEnum.MAGIC_LINK

        assert view_func(organisation_id=grant_recipient.organisation.id) == "OK"
