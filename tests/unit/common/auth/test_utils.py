import pytest

from app.common.security.utils import sanitise_redirect_url


class TestSanitiseRedirectURL:
    @pytest.mark.parametrize(
        "url, expected_url",
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
    def test_redirect_sanitisation(self, app, url, expected_url):
        with app.test_request_context("/", headers={"Host": "funding.communities.gov.localhost:8080"}):
            assert sanitise_redirect_url(url) == expected_url
