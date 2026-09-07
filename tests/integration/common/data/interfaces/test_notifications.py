import uuid

import pytest
from sqlalchemy.exc import NoResultFound

from app.common.data import interfaces
from app.common.data.models import Question
from app.services.notify import NotificationReference


class TestResolveNotificationReference:
    def test_resolves_invitation(self, db_session, factories):
        invitation = factories.invitation.create()
        reference = NotificationReference.from_reference(f"db:invitation:{invitation.id}")

        assert interfaces.notifications.resolve_notification_reference(reference) is invitation

    def test_resolves_polymorphic_model_to_subclass(self, db_session, factories):
        question = factories.question.create()
        reference = NotificationReference.from_reference(f"db:component:{question.id}")

        resolved = interfaces.notifications.resolve_notification_reference(reference)

        assert resolved is question
        assert isinstance(resolved, Question)

    def test_unknown_id_raises(self, db_session):
        reference = NotificationReference.from_reference(f"db:invitation:{uuid.uuid4()}")

        with pytest.raises(NoResultFound):
            interfaces.notifications.resolve_notification_reference(reference)

    def test_unknown_table_raises(self, db_session):
        reference = NotificationReference.from_reference(f"db:not_a_table:{uuid.uuid4()}")

        with pytest.raises(ValueError):
            interfaces.notifications.resolve_notification_reference(reference)
