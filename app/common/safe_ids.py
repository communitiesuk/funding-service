"""Convert UUIDs to a format suitable for using in our expressions engine

Our expression engine expects identifiers to conform to python's variable syntax (ie cannot start with a digit, which
UUIDs might).
"""

# fixme: Ideally we'd implement a protocol like this and derive `SafeQuestionIdMixin` from it, which would ensure that
#        any class that uses the mixin has a `question_id` property. But Python's type hinting system doesn't yet
#        support the union of eg a protocol and a Pydantic BaseModel, so we can't do this. 28/6/25
# class _QuestionIdProtocol(Protocol):
#     question_id: uuid.UUID
import uuid


class SafeQuestionIdMixin:
    # This attribute must be defined on the inheriting class
    question_id: uuid.UUID

    @property
    def safe_qid(self) -> str:
        """
        Returns the question ID in a format that is suitable for using as a Python variable/attribute name, for
        feeding into some of our dynamic systems (form generation, expression evaluation, etc).
        """
        return "q_" + self.question_id.hex

    @staticmethod
    def safe_qid_to_id(safe_qid: str) -> uuid.UUID | None:
        if safe_qid.startswith("q_"):
            return uuid.UUID(safe_qid[2:])

        return None


class SafeCollectionIdMixin:
    # This attribute must be defined on the inheriting class
    collection_id: uuid.UUID

    @property
    def safe_cid(self) -> str:
        """
        Returns the collection ID in a format that is suitable for using as a Python variable/attribute name, for
        feeding into some of our dynamic systems (form generation, expression evaluation, etc).
        """
        return "c_" + self.collection_id.hex

    @staticmethod
    def safe_cid_to_id(safe_cid: str) -> uuid.UUID | None:
        if safe_cid.startswith("c_"):
            return uuid.UUID(safe_cid[2:])

        return None
