from wtforms.fields.core import Field
from wtforms.form import BaseForm
from wtforms.validators import ValidationError


class MaxWords:
    """
    Validates that a field contains no more than a specified number of words.
    """

    def __init__(self, max_words: int, message: str | None = None) -> None:
        self.max_words = max_words
        self.message = message

    def __call__(self, form: BaseForm, field: Field) -> None:
        if not field.data:
            return  # Don't validate empty fields - use DataRequired for that

        words = field.data.split()
        if len(words) > self.max_words:
            message = self.message or f"Must be {self.max_words} words or fewer"
            raise ValidationError(message)


class MinWords:
    """
    Validates that a field contains at least a specified number of words.
    """

    def __init__(self, min_words: int, message: str | None = None) -> None:
        self.min_words = min_words
        self.message = message

    def __call__(self, form: BaseForm, field: Field) -> None:
        if not field.data:
            return  # Don't validate empty fields - use DataRequired for that

        words = field.data.split()
        if len(words) < self.min_words:
            message = self.message or f"Must be {self.min_words} words or more"
            raise ValidationError(message)


class WordRange:
    """
    Validates that a field contains between a minimum and maximum number of words.
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
