from enum import Enum
from typing import Literal

LogFormats = Literal["plaintext", "json"]
LogLevels = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class TNotProvided(Enum):
    token = 0


NOT_PROVIDED = TNotProvided.token
