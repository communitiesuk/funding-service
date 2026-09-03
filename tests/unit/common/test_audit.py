import datetime
from collections.abc import Iterator
from enum import IntEnum, StrEnum
from typing import Any, Literal, get_origin
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.common.audit import (
    AuditEvent,
    DatabaseModelChange,
    SystemEvent,
    UserPermissionsAdded,
    UserPermissionsRemoved,
    _audit_event_adapters,
    _serialize_value,
    parse_audit_event,
)
from app.common.data.types import AuditEventType, RoleEnum


def _all_subclasses(cls: type[AuditEvent]) -> Iterator[type[AuditEvent]]:
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _all_subclasses(subclass)


def _concrete_audit_event_classes() -> list[type[AuditEvent]]:
    return [
        event_class
        for event_class in _all_subclasses(AuditEvent)
        if get_origin(event_class.model_fields["action"].annotation) is Literal
    ]


def _audit_event_classes_parsed_by(schema: Any) -> set[type[AuditEvent]]:
    if isinstance(schema, dict):
        is_audit_event_model = schema.get("type") == "model" and issubclass(schema["cls"], AuditEvent)
        found = {schema["cls"]} if is_audit_event_model else set()
        return found.union(*(_audit_event_classes_parsed_by(value) for value in schema.values()))
    if isinstance(schema, list):
        return set().union(*(_audit_event_classes_parsed_by(item) for item in schema))
    return set()


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


class TestUserPermissionsAddedModel:
    def test_has_correct_event_type_and_action(self, factories):
        user = factories.user.build()

        event = UserPermissionsAdded(
            user_id=user.id,
            grant_recipient_id=uuid4(),
            organisation_id=uuid4(),
            grant_id=uuid4(),
            target_user_id=uuid4(),
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
            resulting_permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )

        assert event.event_type == AuditEventType.USER_MANAGEMENT
        assert event.action == "permissions_added"

    def test_serializes_to_json(self, factories):
        user = factories.user.build()
        grant_recipient_id = uuid4()
        organisation_id = uuid4()
        grant_id = uuid4()
        target_user_id = uuid4()
        invitation_id = uuid4()

        event = UserPermissionsAdded(
            user_id=user.id,
            grant_recipient_id=grant_recipient_id,
            organisation_id=organisation_id,
            grant_id=grant_id,
            target_user_id=target_user_id,
            invitation_id=invitation_id,
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
            resulting_permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )

        json_data = event.model_dump(mode="json")

        assert json_data["user_id"] == str(user.id)
        assert json_data["grant_recipient_id"] == str(grant_recipient_id)
        assert json_data["organisation_id"] == str(organisation_id)
        assert json_data["grant_id"] == str(grant_id)
        assert json_data["target_user_id"] == str(target_user_id)
        assert json_data["permissions"] == ["data-provider", "member"]
        assert json_data["resulting_permissions"] == ["certifier", "data-provider", "member"]
        assert json_data["invitation_id"] == str(invitation_id)
        assert json_data["action"] == "permissions_added"
        assert json_data["event_type"] == "user-management"


class TestUserPermissionsRemovedModel:
    def test_has_correct_event_type_and_action(self, factories):
        user = factories.user.build()

        event = UserPermissionsRemoved(
            user_id=user.id,
            grant_recipient_id=uuid4(),
            organisation_id=uuid4(),
            grant_id=uuid4(),
            target_user_id=uuid4(),
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
            resulting_permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )

        assert event.event_type == AuditEventType.USER_MANAGEMENT
        assert event.action == "permissions_removed"

    def test_serializes_to_json(self, factories):
        user = factories.user.build()
        grant_recipient_id = uuid4()
        organisation_id = uuid4()
        grant_id = uuid4()
        target_user_id = uuid4()

        event = UserPermissionsRemoved(
            user_id=user.id,
            grant_recipient_id=grant_recipient_id,
            organisation_id=organisation_id,
            grant_id=grant_id,
            target_user_id=target_user_id,
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
            resulting_permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )

        json_data = event.model_dump(mode="json")

        assert json_data["user_id"] == str(user.id)
        assert json_data["grant_recipient_id"] == str(grant_recipient_id)
        assert json_data["organisation_id"] == str(organisation_id)
        assert json_data["grant_id"] == str(grant_id)
        assert json_data["target_user_id"] == str(target_user_id)
        assert json_data["permissions"] == ["data-provider", "member"]
        assert json_data["resulting_permissions"] == ["certifier", "data-provider", "member"]
        assert json_data["invitation_id"] is None
        assert json_data["action"] == "permissions_removed"
        assert json_data["event_type"] == "user-management"


class TestParseAuditEvent:
    def test_parses_permissions_added_event(self, factories):
        user = factories.user.build()
        event = UserPermissionsAdded(
            user_id=user.id,
            target_user_id=uuid4(),
            organisation_id=uuid4(),
            grant_id=uuid4(),
            grant_recipient_id=uuid4(),
            invitation_id=uuid4(),
            permissions=[RoleEnum.DATA_PROVIDER],
            resulting_permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER],
        )

        parsed = parse_audit_event(AuditEventType.USER_MANAGEMENT, event.model_dump(mode="json"))

        assert isinstance(parsed, UserPermissionsAdded)
        assert parsed == event

    def test_parses_permissions_removed_event(self, factories):
        user = factories.user.build()
        event = UserPermissionsRemoved(
            user_id=user.id,
            target_user_id=uuid4(),
            organisation_id=None,
            grant_id=None,
            grant_recipient_id=None,
            permissions=[RoleEnum.MEMBER],
            resulting_permissions=[],
        )

        parsed = parse_audit_event(AuditEventType.USER_MANAGEMENT, event.model_dump(mode="json"))

        assert isinstance(parsed, UserPermissionsRemoved)
        assert parsed == event

    def test_invitation_id_defaults_to_none_when_absent(self, factories):
        user = factories.user.build()
        data = UserPermissionsAdded(
            user_id=user.id,
            target_user_id=uuid4(),
            organisation_id=uuid4(),
            grant_id=None,
            grant_recipient_id=None,
            permissions=[RoleEnum.ADMIN],
            resulting_permissions=[RoleEnum.ADMIN],
        ).model_dump(mode="json")
        del data["invitation_id"]

        parsed = parse_audit_event(AuditEventType.USER_MANAGEMENT, data)

        assert parsed.invitation_id is None

    def test_rejects_unknown_action(self, factories):
        user = factories.user.build()
        data = UserPermissionsAdded(
            user_id=user.id,
            target_user_id=uuid4(),
            organisation_id=None,
            grant_id=None,
            grant_recipient_id=None,
            permissions=[RoleEnum.ADMIN],
            resulting_permissions=[RoleEnum.ADMIN],
        ).model_dump(mode="json")
        data["action"] = "team_member_added"

        with pytest.raises(ValidationError):
            parse_audit_event(AuditEventType.USER_MANAGEMENT, data)

    def test_parses_database_model_change(self):
        event = DatabaseModelChange(
            user_id=uuid4(), model_class="Grant", model_id=uuid4(), action="create", changes={"name": "Test Grant"}
        )

        parsed = parse_audit_event(AuditEventType.PLATFORM_ADMIN_DB_EVENT, event.model_dump(mode="json"))

        assert isinstance(parsed, DatabaseModelChange)
        assert parsed == event

    def test_parses_system_event(self):
        event = SystemEvent(
            user_id=uuid4(),
            model_class="UserRole",
            model_id=uuid4(),
            action="delete",
            changes={"user_id": str(uuid4())},
            context={"notification_id": str(uuid4()), "reason": "Permanent delivery failure"},
        )

        parsed = parse_audit_event(AuditEventType.SYSTEM, event.model_dump(mode="json"))

        assert isinstance(parsed, SystemEvent)
        assert parsed == event

    def test_rejects_incomplete_database_model_change(self):
        with pytest.raises(ValidationError):
            parse_audit_event(
                AuditEventType.PLATFORM_ADMIN_DB_EVENT, {"model_class": "Grant", "action": "create", "changes": {}}
            )

    @pytest.mark.parametrize("event_type", list(AuditEventType))
    def test_every_event_type_has_a_parser(self, event_type):
        with pytest.raises(ValidationError):
            parse_audit_event(event_type, {})

    @pytest.mark.parametrize("event_class", _concrete_audit_event_classes(), ids=lambda cls: cls.__name__)
    def test_every_audit_event_class_is_registered_under_its_event_type(self, event_class):
        event_type = event_class.model_fields["event_type"].default
        registered_classes = _audit_event_classes_parsed_by(_audit_event_adapters[event_type].core_schema)
        assert event_class in registered_classes, (
            f"Add {event_class.__name__} to `_audit_event_adapters[{event_type}]` in app/common/audit.py so the "
            "platform admin can parse and render it"
        )


class TestAuditEventFieldOrder:
    @pytest.mark.parametrize("event_class", _concrete_audit_event_classes(), ids=lambda cls: cls.__name__)
    def test_common_fields_come_first(self, event_class):
        assert list(event_class.model_fields)[:4] == ["event_type", "timestamp", "user_id", "action"]
