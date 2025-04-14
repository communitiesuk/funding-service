import pytest

from app.common.auth import SignInForm


class TestSignInForm:
    @pytest.mark.parametrize(
        "redirect_to, expected_clean_redirect_to",
        (
            ("/", "/"),
            ("/blah/blah", "/blah/blah"),
            ("http://funding.communities.gov.localhost:8080/blah", "/blah"),
            ("mailto://funding.communities.gov.localhost:8080/blah", "/"),
            ("http://bad.domain.localhost:8080/blah", "/"),
            ("//blah", "/"),
            ("///blah", "/blah"),
            ("/blah?query=param", "/blah?query=param"),
        ),
    )
    def test_redirect_sanitisation(self, client, redirect_to, expected_clean_redirect_to):
        form = SignInForm()
        form.process(data={"email_address": "test@communities.gov.uk", "redirect_to": redirect_to})
        assert not form.errors
        assert form.redirect_to.data == expected_clean_redirect_to
