# fixme: Ideally we'd implement a protocol like this and derive `SafeQidMixin` from it, which would ensure that
#        any class that uses the mixin has a `question_id` property. But Python's type hinting system doesn't yet
#        support the union of eg a protocol and a Pydantic BaseModel, so we can't do this. 28/6/25
# class _QuestionIdProtocol(Protocol):
#     question_id: uuid.UUID
import uuid

from app.common.utils import slugify


class SafeQidMixin:
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
    def safe_qid_from_id(question_id: uuid.UUID) -> str:
        return "q_" + question_id.hex

    @staticmethod
    def safe_qid_to_id(safe_qid: str) -> uuid.UUID | None:
        if safe_qid.startswith("q_"):
            return uuid.UUID(safe_qid[2:])

        return None


class SafeDidMixin:
    # This attribute must be defined on the inheriting class
    data_source_id: uuid.UUID

    @property
    def safe_did(self) -> str:
        """
        Returns the data source ID in a format that is suitable for using as a Python variable/attribute name, for
        feeding into some of our dynamic systems (form generation, expression evaluation, etc).
        """
        return "d_" + self.data_source_id.hex

    @staticmethod
    def safe_did_from_id(data_source_id: uuid.UUID) -> str:
        return "d_" + data_source_id.hex

    @staticmethod
    def safe_did_to_id(safe_did: str) -> uuid.UUID | None:
        if safe_did.startswith("d_"):
            return uuid.UUID(safe_did[2:])

        return None

    @staticmethod
    def safe_ds_ref_to_id_and_column_name(data_source_reference: str) -> tuple[uuid.UUID, str] | tuple[None, None]:
        if data_source_reference.count(".") != 1:
            return None, None
        safe_did, column_name = data_source_reference.split(".")
        data_source_id = SafeDidMixin.safe_did_to_id(safe_did)
        if data_source_id is None:
            return None, None
        return data_source_id, column_name


def safe_column_id(text: str) -> str:
    """
    Similar to `slugify`, convert a string to a safe Python identifier string containing only lowercase alphanumeric
    characters and underscores (rather than hyphens) and prefaced with `c_`.
    :param text: The string to turn into a safe Python identifier
    :return: The resulting identifier

    For example:
        - "Hello World" -> "c_hello_world"
        - "Special #$@! Characters" -> "c_special_characters"
        - "ångström unicode" -> "c_ngstrm_unicode"
    """
    return "c_" + slugify(text).replace("-", "_")
