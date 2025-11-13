from unittest.mock import Mock, patch

import pytest
from wtforms.validators import ValidationError

from app.common.data.types import RoleEnum
from app.common.forms.validators import (
    AccessGrantFundingEmail,
    CommunitiesEmail,
    FinalOptionExclusive,
    URLWithoutProtocol,
    WordRange,
)


class TestWordRange:
    def _get_mocks(self) -> tuple[Mock, Mock]:
        form = Mock()
        field = Mock()
        field.name = "answer"
        return form, field

    def test_max_words_valid_within_limit(self):
        validator = WordRange(max_words=3)
        form, field = self._get_mocks()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_max_words_invalid_exceeds_limit(self):
        validator = WordRange(max_words=2)
        form, field = self._get_mocks()
        field.data = "This has three words"

        with pytest.raises(ValidationError, match="Answer must be 2 words or fewer"):
            validator(form, field)

    def test_min_words_valid_above_minimum(self):
        validator = WordRange(min_words=2)
        form, field = self._get_mocks()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_min_words_invalid_below_minimum(self):
        validator = WordRange(min_words=5)
        form, field = self._get_mocks()
        field.data = "Too short"

        with pytest.raises(ValidationError, match="Answer must be 5 words or more"):
            validator(form, field)

    def test_meets_exact_range(self):
        validator = WordRange(min_words=2, max_words=2)
        form, field = self._get_mocks()
        field.data = "Two words"

        validator(form, field)

    def test_outside_exact_range(self):
        validator = WordRange(min_words=2, max_words=2)
        form, field = self._get_mocks()
        field.data = "Three words here"

        with pytest.raises(ValidationError, match="Answer must contain exactly 2 words"):
            validator(form, field)

    def test_valid_within_range(self):
        validator = WordRange(min_words=2, max_words=5)
        form, field = self._get_mocks()
        field.data = "Four words total here"

        validator(form, field)  # Should not raise

    def test_invalid_outside_range(self):
        validator = WordRange(min_words=3, max_words=6)
        form, field = self._get_mocks()
        field.data = "Too short"

        with pytest.raises(ValidationError, match="Answer must be between 3 words and 6 words"):
            validator(form, field)

    def test_both_min_words_or_max_words_absent(self):
        with pytest.raises(ValueError):
            WordRange()

    def test_min_words_greater_than_max_words(self):
        with pytest.raises(ValueError):
            WordRange(min_words=2, max_words=1)

    def test_field_display_name(self):
        validator = WordRange(min_words=3, field_display_name="test display name")
        form, field = self._get_mocks()
        field.data = "Too short"

        with pytest.raises(ValidationError, match="Test display name must be 3 words or more"):
            validator(form, field)


class TestCommunitiesEmailValidator:
    def setup_method(self):
        self.validator = CommunitiesEmail()
        self.field = Mock()
        self.field.gettext = lambda msg: msg
        self.form = Mock()
        self.default_domains = ["@communities.gov.uk", "@test.communities.gov.uk"]

    def _call_validator(self, email):
        self.field.data = email
        self.validator(self.form, self.field)

    def test_valid_email_with_allowed_domain(self):
        self._call_validator("test@communities.gov.uk")
        self._call_validator("test@test.communities.gov.uk")

    def test_valid_email_with_disallowed_domain(self):
        with pytest.raises(
            ValidationError, match="Email address must end with @communities.gov.uk or @test.communities.gov.uk"
        ):
            self._call_validator("outsider@external.com")

    def test_invalid_email_format(self):
        with pytest.raises(
            ValidationError, match="Enter an email address in the correct format, like name@example.com"
        ):
            self._call_validator("bad-email-format")

    def test_case_insensitive_domain_match(self):
        self._call_validator("Staff@Communities.Gov.Uk")

    def test_missing_internal_domains_config(self, app):
        with pytest.raises(KeyError), patch.dict(app.config, {}, clear=True):
            self.field.data = "user@anywhere.com"
            self.validator(self.form, self.field)


class TestURLWithoutProtocol:
    @pytest.mark.parametrize(
        "url",
        [
            "www.google.com",
            "http://www.google.com",
            "https://www.google.com",
            "https://gov.uk",
            "https://gov.uk/blog/foo",
            "https://gov.uk/blog/foo?hmmm",
            "https://gov.uk/blog/foo?hmmm=something",
            pytest.param("blah", marks=pytest.mark.xfail()),
            pytest.param("http://", marks=pytest.mark.xfail()),
            pytest.param("blah-foo", marks=pytest.mark.xfail()),
        ],
    )
    def test_urls(self, url):
        form = Mock()
        field = Mock()
        field.data = url
        validator = URLWithoutProtocol()

        assert validator(form, field)


class TestFinalOptionExclusive:
    def _get_mocks(self) -> tuple[FinalOptionExclusive, Mock, Mock]:
        form = Mock()
        field = Mock()
        validator = FinalOptionExclusive(question_name="test question")
        return validator, form, field

    def test_valid_when_only_final_option_selected(self):
        options_list = [("option-a", "Option A"), ("option-b", "Option B"), ("other", "Other")]
        validator, form, field = self._get_mocks()

        field.data = ["other"]
        field.choices = options_list

        validator(form, field)

    def test_valid_when_non_final_options_selected(self):
        options_list = [("option-a", "Option A"), ("option-b", "Option B"), ("other", "Other")]
        validator, form, field = self._get_mocks()

        field.data = ["option-a", "option-b"]
        field.choices = options_list

        validator(form, field)

    def test_invalid_when_final_option_and_others_selected(self):
        options_list = [("option-a", "Option A"), ("option-b", "Option B"), ("other", "Other")]
        validator, form, field = self._get_mocks()

        field.data = ["option-a", "other"]
        field.choices = options_list

        with pytest.raises(ValidationError, match="Select test question, or select Other"):
            validator(form, field)

    def test_custom_message_used_if_provided(self):
        options_list = [("option-a", "Option A"), ("option-b", "Option B"), ("other", "Other")]
        validator = FinalOptionExclusive(question_name="ignored", message="This is a different error message")
        _, form, field = self._get_mocks()

        field.data = ["option-a", "other"]
        field.choices = options_list

        with pytest.raises(ValidationError, match="This is a different error message"):
            validator(form, field)

    def test_no_validation_error_when_field_is_empty(self):
        options_list = [("option-a", "Option A"), ("option-b", "Option B"), ("other", "Other")]
        validator, form, field = self._get_mocks()
        field.data = []
        field.choices = options_list

        validator(form, field)


class TestAccessGrantFundingEmail:
    def _get_mocks(self) -> tuple[AccessGrantFundingEmail, Mock, Mock]:
        form = Mock()
        field = Mock()
        validator = AccessGrantFundingEmail()
        return validator, form, field

    def test_empty_field_returns(self):
        validator, form, field = self._get_mocks()
        field.data = ""

        validator(form, field)

    def test_internal_email_domain_returns(self):
        validator, form, field = self._get_mocks()
        field.data = "test@communities.gov.uk"

        validator(form, field)

    def test_unknown_user_fails(self, factories, mocker):
        validator, form, field = self._get_mocks()

        mocker.patch("app.common.forms.validators.interfaces.user.get_user_by_email", return_value=None)

        field.data = "different_user@localgov.gov.uk"

        with pytest.raises(
            ValidationError,
            match=(
                "The email address you entered does not have access to this service. "
                "Check the email address is correct or request access."
            ),
        ):
            validator(form, field)

    def test_user_without_grant_recipient_org_fails(self, factories, mocker):
        user = factories.user.build(email="test@localgov.gov.uk")
        validator, form, field = self._get_mocks()

        mocker.patch("app.common.forms.validators.interfaces.user.get_user_by_email", return_value=user)

        field.data = user.email

        with pytest.raises(
            ValidationError,
            match=(
                "The email address you entered does not have access to this service. "
                "Check the email address is correct or request access."
            ),
        ):
            validator(form, field)

    def test_user_with_grant_recipient_org_passes(self, factories, mocker):
        recipient_org = factories.organisation.build(can_manage_grants=False)
        grant_org = factories.organisation.build(can_manage_grants=True)
        grant = factories.grant.build(organisation=grant_org)
        grant_recipient = factories.grant_recipient.build(grant=grant, organisation=recipient_org)
        user = factories.user.build(email="test@localgov.gov.uk")
        factories.user_role.build(
            user=user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )
        user.get_grant_recipients = mocker.Mock(return_value=[grant_recipient])

        validator, form, field = self._get_mocks()

        mocker.patch("app.common.forms.validators.interfaces.user.get_user_by_email", return_value=user)

        field.data = user.email

        validator(form, field)
