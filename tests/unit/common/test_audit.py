import datetime
from enum import IntEnum, StrEnum
from uuid import uuid4

from app.common.audit import (
    DatabaseModelChange,
    _serialize_value,
)
from app.common.data.types import AuditEventType


class TestSerializeValue:
    def test_serializes_uuid_to_string(self):
        test_uuid = uuid4()
        result = _serialize_value(test_uuid)
        assert result == str(test_uuid)
        assert isinstance(result, str)

    def test_serializes_datetime_to_isoformat(self):
        test_datetime = datetime.datetime(2025, 1, 15, 10, 30, 45)
        result = _serialize_value(test_datetime)
        assert result == "2025-01-15T10:30:45"

    def test_serializes_str_enum_to_name(self):
        class TestStrEnum(StrEnum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        result = _serialize_value(TestStrEnum.ACTIVE)
        assert result == "ACTIVE"

    def test_serializes_int_enum_to_name(self):
        class TestIntEnum(IntEnum):
            LOW = 1
            HIGH = 10

        result = _serialize_value(TestIntEnum.HIGH)
        assert result == "HIGH"

    def test_serializes_list_recursively(self):
        test_uuid = uuid4()
        test_list = [test_uuid, "string", 123]
        result = _serialize_value(test_list)
        assert result == [str(test_uuid), "string", 123]

    def test_serializes_tuple_recursively(self):
        test_uuid = uuid4()
        test_tuple = (test_uuid, "value")
        result = _serialize_value(test_tuple)
        assert result == [str(test_uuid), "value"]

    def test_returns_string_unchanged(self):
        result = _serialize_value("test string")
        assert result == "test string"

    def test_returns_int_unchanged(self):
        result = _serialize_value(42)
        assert result == 42

    def test_returns_float_unchanged(self):
        result = _serialize_value(3.14)
        assert result == 3.14

    def test_returns_none_unchanged(self):
        result = _serialize_value(None)
        assert result is None

    def test_returns_bool_unchanged(self):
        assert _serialize_value(True) is True
        assert _serialize_value(False) is False

    def test_does_not_iterate_over_bytes(self):
        test_bytes = b"test bytes"
        result = _serialize_value(test_bytes)
        assert result == test_bytes


class TestDatabaseModelChangeModel:
    def test_has_correct_event_type(self, factories):
        user = factories.user.build()

        event = DatabaseModelChange(
            user_id=user.id,
            model_class="TestModel",
            model_id=uuid4(),
            action="create",
            changes={"field": "value"},
        )

        assert event.event_type == AuditEventType.PLATFORM_ADMIN_DB_EVENT

    def test_timestamp_defaults_to_utcnow(self, factories):
        user = factories.user.build()
        before = datetime.datetime.now(datetime.timezone.utc)

        event = DatabaseModelChange(
            user_id=user.id,
            model_class="TestModel",
            model_id=uuid4(),
            action="update",
            changes={},
        )

        after = datetime.datetime.now(datetime.timezone.utc)
        assert before <= event.timestamp <= after

    def test_serializes_to_json(self, factories):
        user = factories.user.build()
        model_id = uuid4()

        event = DatabaseModelChange(
            user_id=user.id,
            model_class="Grant",
            model_id=model_id,
            action="delete",
            changes={"name": "Test"},
        )

        json_data = event.model_dump(mode="json")

        assert json_data["user_id"] == str(user.id)
        assert json_data["model_id"] == str(model_id)
        assert json_data["model_class"] == "Grant"
        assert json_data["action"] == "delete"
        assert json_data["event_type"] == "platform-admin-db-event"
