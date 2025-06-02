from unittest.mock import Mock

import pytest
from wtforms.validators import ValidationError

from app.common.forms.validators import WordRange


class TestWordRange:
    def test_max_words_valid_within_limit(self):
        validator = WordRange(0, 3)
        form = Mock()
        field = Mock()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_max_words_invalid_exceeds_limit(self):
        validator = WordRange(0, 2)
        form = Mock()
        field = Mock()
        field.data = "This has three words"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_min_words_valid_above_minimum(self):
        validator = WordRange(2, 100)
        form = Mock()
        field = Mock()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_min_words_invalid_below_minimum(self):
        validator = WordRange(5, 100)
        form = Mock()
        field = Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_valid_within_range(self):
        validator = WordRange(2, 5)
        form = Mock()
        field = Mock()
        field.data = "Four words total here"

        validator(form, field)  # Should not raise

    def test_invalid_outside_range(self):
        validator = WordRange(3, 6)
        form = Mock()
        field = Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_empty_field_passes(self):
        validator = WordRange(2, 5)
        form = Mock()
        field = Mock()
        field.data = ""

        validator(form, field)  # Should not raise

    def test_custom_message(self):
        custom_message = "Word count is not valid"
        validator = WordRange(2, 4, message=custom_message)
        form = Mock()
        field = Mock()
        field.data = "Too many words in this sentence"

        with pytest.raises(ValidationError, match=custom_message):
            validator(form, field)

    def test_default_message(self):
        validator = WordRange(2, 4)
        form = Mock()
        field = Mock()
        field.data = "Single"

        with pytest.raises(ValidationError, match="Must be between 2 and 4 words"):
            validator(form, field)
