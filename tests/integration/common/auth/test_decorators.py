import pytest
from flask_login import login_user
from werkzeug.exceptions import Forbidden, InternalServerError

from app.common.auth.decorators import (
    login_required,
    mhclg_login_required,
    platform_admin_role_required,
    redirect_if_authenticated,
)
from app.common.data.types import RoleEnum


class TestLoginRequired:
    def test_logged_in_user_gets_response(self, app, factories):
        @login_required
        def test_login_required():
            return "OK"

        user = factories.user.create(email="test@anything.com", azure_ad_subject_id=None)

        login_user(user)
        response = test_login_required()
        assert response == "OK"

    def test_anonymous_user_gets_redirect(self, app):
        @login_required
        def test_login_required():
            return "OK"

        response = test_login_required()
        assert response.status_code == 302


class TestMHCLGLoginRequired:
    def test_logged_in_mhclg_user_gets_response(self, app, factories):
        @mhclg_login_required
        def test_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        login_user(user)
        response = test_login_required()
        assert response == "OK"

    def test_non_mhclg_user_is_forbidden(self, app, factories):
        @mhclg_login_required
        def test_login_required():
            return "OK"

        user = factories.user.create(email="test@anything.com")

        with pytest.raises(Forbidden):
            login_user(user)
            test_login_required()

    def test_anonymous_user_gets_redirect(self, app):
        @mhclg_login_required
        def test_login_required():
            return "OK"

        response = test_login_required()
        assert response.status_code == 302


class TestPlatformAdminRoleRequired:
    def test_logged_in_platform_admin_gets_response(self, app, factories):
        @platform_admin_role_required
        def test_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.ADMIN)

        login_user(user)
        response = test_login_required()
        assert response == "OK"

    def test_non_platform_admin_is_forbidden(self, app, factories):
        @platform_admin_role_required
        def test_login_required():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        with pytest.raises(Forbidden):
            login_user(user)
            test_login_required()

    def test_anonymous_user_gets_redirect(self, app):
        @platform_admin_role_required
        def test_login_required():
            return "OK"

        response = test_login_required()
        assert response.status_code == 302


class TestRedirectIfAuthenticated:
    def test_authenticated_user_gets_redirect(self, app, factories):
        @redirect_if_authenticated
        def test_authenticated_redirect():
            return "OK"

        user = factories.user.create(email="test@communities.gov.uk")

        login_user(user)
        response = test_authenticated_redirect()
        assert response.status_code == 302

    def test_external_authenticated_user_gets_403(self, app, factories):
        @redirect_if_authenticated
        def test_authenticated_redirect():
            return "OK"

        user = factories.user.create(email="test@anything.com")

        with pytest.raises(InternalServerError):
            login_user(user)
            test_authenticated_redirect()

    def test_anonymous_user_gets_response(self, app):
        @redirect_if_authenticated
        def test_authenticated_redirect():
            return "OK"

        response = test_authenticated_redirect()
        assert response == "OK"
