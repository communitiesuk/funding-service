# fixme: Ideally we'd implement a protocol like this and derive `SafeQidMixin` from it, which would ensure that
#        any class that uses the mixin has a `question_id` property. But Python's type hinting system doesn't yet
#        support the union of eg a protocol and a Pydantic BaseModel, so we can't do this. 28/6/25
# class _QuestionIdProtocol(Protocol):
#     question_id: uuid.UUID
import uuid
from typing import Optional


class SafeQidMixin:
    # This attribute must be defined on the inheriting class
    question_id: uuid.UUID
    add_another_index: Optional[int] = None

    @property
    def safe_qid(self) -> str:
        """
        Returns the question ID in a format that is suitable for using as a Python variable/attribute name, for
        feeding into some of our dynamic systems (form generation, expression evaluation, etc).
        """
        return (
            "q_" + self.question_id.hex + (f"_{self.add_another_index}" if self.add_another_index is not None else "")
        )
