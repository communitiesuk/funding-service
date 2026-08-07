from flask import Flask

from app.common.auth.forms import SignInForm


class TestSignInForm:
    def test_requires_existing_grant_recipient_by_default(self, app: Flask, mocker):
        mocker.patch("app.common.forms.validators.interfaces.user.get_user_by_email", return_value=None)

        form = SignInForm(data={"email_address": "new-applicant@example.com"})

        assert form.validate() is False
        assert form.email_address.errors == [
            "The email address you entered does not have access to this service. "
            "Check the email address is correct or request access."
        ]

    def test_requires_existing_grant_recipient_by_default_passes_when_user_exists(self, app: Flask, mocker):
        user = mocker.Mock()
        mocker.patch("app.common.forms.validators.interfaces.user.get_user_by_email", return_value=user)

        form = SignInForm(data={"email_address": "existing-user@example.com"})

        assert form.validate() is True
        assert form.email_address.errors == []

    def test_public_sign_off_allows_unknown_email(self, app: Flask, mocker):
        get_user_by_email = mocker.patch("app.common.forms.validators.interfaces.user.get_user_by_email")

        form = SignInForm(is_public_sign_in=True, data={"email_address": "new-applicant@example.com"})

        assert form.validate() is True
        assert form.email_address.errors == []
        get_user_by_email.assert_not_called()

    def test_public_sign_off_still_requires_a_valid_email(self, app: Flask):
        form = SignInForm(is_public_sign_in=True, data={"email_address": "not-an-email"})

        assert form.validate() is False
        assert form.email_address.errors == ["Enter an email address in the correct format, like name@example.com"]

    def test_public_sign_off_still_requires_an_email(self, app: Flask):
        form = SignInForm(is_public_sign_in=True, data={"email_address": ""})

        assert form.validate() is False
        assert form.email_address.errors == ["Enter your email address"]
