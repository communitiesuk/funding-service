import pytest
from email_validator import EmailNotValidError


class TestEmailDomain:
    def test_email_domain(self, factories):
        user = factories.user.build(email="test@example-org.com")

        assert user.email_domain == "example-org.com"

    def test_email_domain_with_subdomain(self, factories):
        user = factories.user.build(email="test@sub.example-org.com")

        assert user.email_domain == "sub.example-org.com"

    def test_email_domain_with_broken_email_address(self, factories):
        user = factories.user.build(email="testexample-org.com")

        with pytest.raises(EmailNotValidError):
            _ = user.email_domain
