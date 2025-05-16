import datetime

from sqlalchemy import func, select

from app.common.data import interfaces


class TestCreateMagicLink:
    def test_create_magic_link(self, db_session, factories):
        user = factories.user.create()

        magic_link = interfaces.magic_link.create_magic_link(user, redirect_to_path="/")

        assert magic_link.user == user

    def test_create_magic_link_expiry(self, db_session, factories):
        user = factories.user.create()

        magic_link = interfaces.magic_link.create_magic_link(user, redirect_to_path="/")

        # FIXME: if/when FSPT-366 is done
        should_expire_at = db_session.scalar(select(func.current_timestamp() + datetime.timedelta(minutes=15))).replace(
            tzinfo=None
        )
        assert magic_link.expires_at_utc == should_expire_at

    def test_create_magic_link_expires_other_magic_links_for_the_user(self, db_session, factories):
        old_magic_link = factories.magic_link.create()
        expiry = old_magic_link.expires_at_utc

        interfaces.magic_link.create_magic_link(user=old_magic_link.user, redirect_to_path="/")

        now = db_session.scalar(func.current_timestamp()).replace(tzinfo=None)
        assert expiry != now
        assert old_magic_link.expires_at_utc == now


class TestGetMagicLink:
    def test_get_magic_link_by_id(self, db_session, factories):
        magic_link = factories.magic_link.create()

        retrieved_magic_link = interfaces.magic_link.get_magic_link(id_=magic_link.id)

        assert magic_link is retrieved_magic_link

    def test_get_magic_link_by_code(self, db_session, factories):
        magic_link = factories.magic_link.create()

        retrieved_magic_link = interfaces.magic_link.get_magic_link(code=magic_link.code)

        assert magic_link is retrieved_magic_link


class TestClaimMagicLink:
    def test_claim_magic_link(self, db_session, factories):
        magic_link = factories.magic_link.create()
        now = db_session.scalar(func.current_timestamp()).replace(tzinfo=None)
        assert magic_link.claimed_at_utc is None

        interfaces.magic_link.claim_magic_link(magic_link)

        assert magic_link.claimed_at_utc == now
