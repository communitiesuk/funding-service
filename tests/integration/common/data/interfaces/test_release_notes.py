import datetime

from app.common.data import interfaces


class TestGetPublishedReleaseNotes:
    def test_returns_empty_when_no_release_notes_exist(self, db_session):
        assert interfaces.release_notes.get_published_release_notes() == []

    def test_returns_only_published_release_notes(self, db_session, factories):
        published = factories.release_note.create(is_published=True)
        factories.release_note.create(is_published=False)

        assert interfaces.release_notes.get_published_release_notes() == [published]

    def test_orders_release_notes_most_recent_first(self, db_session, factories):
        middle = factories.release_note.create(release_date=datetime.date(2026, 6, 1), is_published=True)
        oldest = factories.release_note.create(release_date=datetime.date(2026, 5, 1), is_published=True)
        newest = factories.release_note.create(release_date=datetime.date(2026, 7, 1), is_published=True)

        assert interfaces.release_notes.get_published_release_notes() == [newest, middle, oldest]
