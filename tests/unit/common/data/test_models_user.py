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


class TestCanShareEmailDomain:
    @pytest.mark.parametrize(
        "email",
        [
            "someone@gmail.com",
            "someone@hotmail.co.uk",
            "someone@outlook.com",
            "someone@yahoo.co.uk",
            "someone@GMAIL.com",
        ],
    )
    def test_shared_email_providers_cannot_be_shared(self, factories, email):
        user = factories.user.build(email=email)

        assert user.can_share_email_domain is False

    @pytest.mark.parametrize(
        "email",
        [
            "someone@no-org.com",
            "someone@communities.gov.uk",
            "someone@sub.example-org.com",
        ],
    )
    def test_organisation_domains_can_be_shared(self, factories, email):
        user = factories.user.build(email=email)

        assert user.can_share_email_domain is True
