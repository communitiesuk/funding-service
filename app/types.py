from collections import namedtuple
from enum import Enum, StrEnum
from typing import Literal, TypedDict

LogFormats = Literal["plaintext", "json"]
LogLevels = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class TNotProvided(Enum):
    token = 0


NOT_PROVIDED = TNotProvided.token


class FlashMessageType(StrEnum):
    DEPENDENCY_ORDER_ERROR = "dependency_order_error"
    DATA_SOURCE_ITEM_DEPENDENCY_ERROR = "data_source_item_dependency_error"
    SUBMISSION_TESTING_COMPLETE = "submission_testing_complete"
    QUESTION_CREATED = "question_created"
    NESTED_GROUP_ERROR = "nested_group_error"
    SUBMISSION_SIGN_OFF_DECLINED = "submission_sign_off_declined"


TRadioItem = TypedDict("TRadioItem", {"key": str, "label": str})


ResolvedEndpoint = namedtuple("ResolvedEndpoint", ["name", "kwargs"])
