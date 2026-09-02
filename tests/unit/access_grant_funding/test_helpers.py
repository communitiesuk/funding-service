import pytest

from app.access_grant_funding.helpers import can_share_email_domain


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
    def test_shared_email_providers_are_not_offered_the_question(self, factories, email):
        user = factories.user.build(email=email)

        assert can_share_email_domain(user) is False

    @pytest.mark.parametrize(
        "email",
        [
            "someone@no-org.com",
            "someone@communities.gov.uk",
            "someone@sub.example-org.com",
        ],
    )
    def test_organisation_domains_are_offered_the_question(self, factories, email):
        user = factories.user.build(email=email)

        assert can_share_email_domain(user) is True
