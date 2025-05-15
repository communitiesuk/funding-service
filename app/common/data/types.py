import enum

json_scalars = str | int | float | bool


class DataType(enum.Enum):
    TEXT = "TEXT"
    EMAIL = "EMAIL"
    PHONE_NUMBER = "PHONE_NUMBER"
    NUMBER = "NUMBER"
    ADDRESS = "ADDRESS"
    URL = "URL"


class ConditionType(enum.Enum):
    ANSWER_EQUALS = "="
    ANSWER_NOT_EQUALS = "!="


class SubmissionType(enum.Enum):
    CREATED = "Created"
    COMPLETED = "Completed"
