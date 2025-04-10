from sqlalchemy import func, select

from app.common.data import interfaces
from app.common.data.models import User


class TestGetOrCreateUser:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"

    def test_get_existing_user(self, db_session, factories):
        factories.user.create(email="test@communities.gov.uk")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_or_create_user(email_address="test@communities.gov.uk")

        assert db_session.scalar(select(func.count()).select_from(User)) == 1
        assert user.email == "test@communities.gov.uk"
