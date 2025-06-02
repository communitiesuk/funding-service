from wtforms.fields.core import Field
from wtforms.form import BaseForm
from wtforms.validators import ValidationError


class WordRange:
    """
    Validates that the number of words in a field's data is within a specified range.
    """

    def __init__(self, min_words: int, max_words: int, message: str | None = None) -> None:
        self.min_words = min_words
        self.max_words = max_words
        self.message = message

    def __call__(self, form: BaseForm, field: Field) -> None:
        if not field.data:
            return  # Don't validate empty fields - use DataRequired for that

        words = field.data.split()
        word_count = len(words)

        if word_count < self.min_words or word_count > self.max_words:
            message = self.message or f"Must be between {self.min_words} and {self.max_words} words"
            raise ValidationError(message)
