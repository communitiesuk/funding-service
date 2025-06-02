from wtforms.fields.core import Field
from wtforms.form import BaseForm
from wtforms.validators import ValidationError


class WordRange:
    """
    Validates that the number of words in a field's data is within a specified range.
    """

    def __init__(
        self,
        min_words: int | None = None,
        max_words: int | None = None,
        field_display_name: str | None = None,
    ) -> None:
        if min_words is None and max_words is None:
            raise ValueError("min_words and max_words cannot both be None")
        if min_words is not None and max_words is not None and max_words < min_words:
            raise ValueError("max_words cannot be less than min_words")
        self.min_words = min_words
        self.max_words = max_words
        self.field_display_name = field_display_name

    def __call__(self, form: BaseForm, field: Field) -> None:
        if not field.data:
            return  # Don't validate empty fields - use DataRequired for that

        words = field.data.split()
        word_count = len(words)
        field_display_name = self.field_display_name or field.name

        if self.min_words is not None and self.max_words is not None:
            if word_count < self.min_words or word_count > self.max_words:
                raise ValidationError(f"{field_display_name} must be between {self.min_words} and {self.max_words}")

        if self.min_words is not None:
            if word_count < self.min_words:
                raise ValidationError(f"{field_display_name} must be {self.min_words} words or more")

        if self.max_words is not None:
            if word_count > self.max_words:
                raise ValidationError(f"{field_display_name} must be {self.max_words} words or less")
