import enum

json_scalars = str | int | float | bool


class DataType(enum.Enum):
    TEXT = "TEXT"
    INT = "INT"
    CONTACT_DETAILS = "CONTACT_DETAILS"


class ConditionType(enum.Enum):
    ANSWER_EQUALS = "="
    ANSWER_NOT_EQUALS = "!="


class SubmissionType(enum.Enum):
    CREATED = "Created"
    COMPLETED = "Completed"
