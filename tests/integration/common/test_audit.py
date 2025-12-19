from app.common.audit import (
    DatabaseModelChange,
    create_database_model_change_for_create,
    create_database_model_change_for_delete,
    create_database_model_change_for_update,
)
from app.common.data.types import GrantStatusEnum


class TestCreateDatabaseModelChangeForUpdate:
    def test_returns_none_when_no_changes(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create()

        db_session.flush()
        db_session.expire(grant)

        result = create_database_model_change_for_update(grant, user)
        assert result is None

    def test_returns_event_with_changes(self, factories, db_session):
        from app.common.data.models import Grant

        user = factories.user.create()
        grant = factories.grant.create(name="Original Name")
        grant_id = grant.id

        db_session.commit()
        db_session.expire_all()

        fetched_grant = db_session.get(Grant, grant_id)
        fetched_grant.name = "Updated Name"

        result = create_database_model_change_for_update(fetched_grant, user)

        assert result is not None
        assert isinstance(result, DatabaseModelChange)
        assert result.user_id == user.id
        assert result.model_class == "Grant"
        assert result.model_id == grant_id
        assert result.action == "update"
        assert "name" in result.changes
        assert result.changes["name"]["old"] == "Original Name"
        assert result.changes["name"]["new"] == "Updated Name"

    def test_excludes_timestamp_fields_from_changes(self, factories, db_session):
        from app.common.data.models import Grant

        user = factories.user.create()
        grant = factories.grant.create()
        grant_id = grant.id

        db_session.commit()
        db_session.expire_all()

        fetched_grant = db_session.get(Grant, grant_id)
        fetched_grant.name = "Changed Name"

        result = create_database_model_change_for_update(fetched_grant, user)

        assert result is not None
        assert "created_at_utc" not in result.changes
        assert "updated_at_utc" not in result.changes

    def test_tracks_enum_changes(self, factories, db_session):
        from app.common.data.models import Grant

        user = factories.user.create()
        grant = factories.grant.create(status=GrantStatusEnum.DRAFT)
        grant_id = grant.id

        db_session.commit()
        db_session.expire_all()

        fetched_grant = db_session.get(Grant, grant_id)
        fetched_grant.status = GrantStatusEnum.LIVE

        result = create_database_model_change_for_update(fetched_grant, user)

        assert result is not None
        assert "status" in result.changes
        assert result.changes["status"]["old"] == "DRAFT"
        assert result.changes["status"]["new"] == "LIVE"


class TestCreateDatabaseModelChangeForCreate:
    def test_returns_event_with_snapshot(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create(name="New Grant", code="NEW-001")

        result = create_database_model_change_for_create(grant, user)

        assert isinstance(result, DatabaseModelChange)
        assert result.user_id == user.id
        assert result.model_class == "Grant"
        assert result.model_id == grant.id
        assert result.action == "create"
        assert result.changes["name"] == "New Grant"
        assert result.changes["code"] == "NEW-001"

    def test_excludes_timestamp_fields_from_snapshot(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create()

        result = create_database_model_change_for_create(grant, user)

        assert "created_at_utc" not in result.changes
        assert "updated_at_utc" not in result.changes

    def test_serializes_uuid_fields(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create()

        result = create_database_model_change_for_create(grant, user)

        assert result.changes["id"] == str(grant.id)
        assert result.changes["organisation_id"] == str(grant.organisation_id)

    def test_serializes_enum_fields(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)

        result = create_database_model_change_for_create(grant, user)

        assert result.changes["status"] == "LIVE"


class TestCreateDatabaseModelChangeForDelete:
    def test_returns_event_with_snapshot(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create(name="Grant To Delete", code="DEL-001")

        result = create_database_model_change_for_delete(grant, user)

        assert isinstance(result, DatabaseModelChange)
        assert result.user_id == user.id
        assert result.model_class == "Grant"
        assert result.model_id == grant.id
        assert result.action == "delete"
        assert result.changes["name"] == "Grant To Delete"
        assert result.changes["code"] == "DEL-001"

    def test_excludes_timestamp_fields_from_snapshot(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create()

        result = create_database_model_change_for_delete(grant, user)

        assert "created_at_utc" not in result.changes
        assert "updated_at_utc" not in result.changes
