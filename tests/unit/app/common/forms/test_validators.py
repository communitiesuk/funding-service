from unittest.mock import Mock

import pytest
from wtforms.validators import ValidationError

from app.common.forms.validators import MaxWords, MinWords, WordRange


class TestMaxWords:
    def test_valid_within_limit(self):
        validator = MaxWords(3)
        form = Mock()
        field = Mock()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_invalid_exceeds_limit(self):
        validator = MaxWords(2)
        form = Mock()
        field = Mock()
        field.data = "This has three words"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_empty_field_passes(self):
        validator = MaxWords(5)
        form = Mock()
        field = Mock()
        field.data = ""

        validator(form, field)  # Should not raise


class TestMinWords:
    def test_valid_above_minimum(self):
        validator = MinWords(2)
        form = Mock()
        field = Mock()
        field.data = "Three words here"

        validator(form, field)  # Should not raise

    def test_invalid_below_minimum(self):
        validator = MinWords(5)
        form = Mock()
        field = Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_empty_field_passes(self):
        validator = MinWords(3)
        form = Mock()
        field = Mock()
        field.data = ""

        validator(form, field)  # Should not raise


class TestWordRange:
    def test_valid_within_range(self):
        validator = WordRange(2, 5)
        form = Mock()
        field = Mock()
        field.data = "Four words total here"

        validator(form, field)  # Should not raise

    def test_invalid_below_range(self):
        validator = WordRange(3, 6)
        form = Mock()
        field = Mock()
        field.data = "Too short"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_invalid_above_range(self):
        validator = WordRange(1, 3)
        form = Mock()
        field = Mock()
        field.data = "This sentence has too many words"

        with pytest.raises(ValidationError):
            validator(form, field)

    def test_empty_field_passes(self):
        validator = WordRange(2, 5)
        form = Mock()
        field = Mock()
        field.data = ""

        validator(form, field)  # Should not raise
