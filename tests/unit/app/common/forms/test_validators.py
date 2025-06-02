from unittest.mock import Mock

import pytest
from wtforms.validators import ValidationError

from app.common.forms.validators import WordRange


class TestWordRange:
    def test_max_words_valid_within_limit(self):
        validator = WordRange(max_words=3)
        form, field = Mock(), Mock()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_max_words_invalid_exceeds_limit(self):
        validator = WordRange(max_words=2)
        form, field = Mock(), Mock()
        field.data = "This has three words"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_min_words_valid_above_minimum(self):
        validator = WordRange(min_words=2)
        form, field = Mock(), Mock()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_min_words_invalid_below_minimum(self):
        validator = WordRange(min_words=5)
        form, field = Mock(), Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_valid_within_range(self):
        validator = WordRange(min_words=2, max_words=5)
        form, field = Mock(), Mock()
        field.data = "Four words total here"

        validator(form, field)  # Should not raise

    def test_invalid_outside_range(self):
        validator = WordRange(min_words=3, max_words=6)
        form, field = Mock(), Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_both_min_words_or_max_words_absent(self):
        with pytest.raises(ValueError):
            WordRange()

    def test_min_words_greater_than_max_words(self):
        with pytest.raises(ValueError):
            WordRange(min_words=2, max_words=1)

    def test_field_display_name(self):
        validator = WordRange(min_words=3, field_display_name="Test display name")
        form, field = Mock(), Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError, match="Test display name must be 3 words or more"):
            validator(form, field)
