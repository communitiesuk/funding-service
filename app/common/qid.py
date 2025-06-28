import uuid

# fixme: Ideally we'd implement a protocol like this and derive `SafeQidMixin` from it, which would ensure that
#        any class that uses the mixin has a `question_id` property. But Python's type hinting system doesn't yet
#        support the union of eg a protocol and a Pydantic BaseModel, so we can't do this. 28/6/25
# class _QuestionIdProtocol(Protocol):
#     question_id: uuid.UUID


class SafeQidMixin:
    @property
    def safe_qid(self) -> str:
        """
        Returns the question ID in a format that is suitable for using as a Python variable/attribute name, for
        feeding into some of our dynamic systems (form generation, expression evaluation, etc).
        """
        return transform_uuid_to_qid(self.question_id)  # type: ignore[attr-defined]


def transform_uuid_to_qid(id_: uuid.UUID) -> str:
    """
    Returns the UUID in a format that is suitable for using as a Python variable/attribute name, for feeding into some
    of our dynamic systems (form generation, expression evaluation, etc).
    """
    return "q_" + id_.hex
