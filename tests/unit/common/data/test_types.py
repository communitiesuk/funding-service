from app import CollectionStatusEnum
from app.common.data.types import QuestionDataOptions, QuestionDataOptionsPostgresType


class TestCollectionStatusEnum:
    def test_lt_returns_false_when_equal(self):
        assert (CollectionStatusEnum.DRAFT < CollectionStatusEnum.DRAFT) is False

    def test_gt_returns_false_when_equal(self):
        assert (CollectionStatusEnum.DRAFT > CollectionStatusEnum.DRAFT) is False

    def test_lt_returns_true(self):
        assert (CollectionStatusEnum.DRAFT < CollectionStatusEnum.CLOSED) is True

    def test_gt_returns_false(self):
        assert (CollectionStatusEnum.DRAFT > CollectionStatusEnum.CLOSED) is False

    def test_gt_returns_true(self):
        assert (CollectionStatusEnum.CLOSED > CollectionStatusEnum.DRAFT) is True

    def test_lt_returns_false(self):
        assert (CollectionStatusEnum.CLOSED < CollectionStatusEnum.DRAFT) is False

    def test_sort_by_status(self):
        input = [
            CollectionStatusEnum.CLOSED,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.CLOSED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.SCHEDULED,
        ]
        expected = [
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
            CollectionStatusEnum.CLOSED,
        ]
        assert sorted(input) == expected


class TestQuestionDataOptionsPostgresType:
    def test_defaults(self):
        options = QuestionDataOptions()
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {}

    def test_allow_decimals(self):
        options = QuestionDataOptions(allow_decimals=True)
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {"allow_decimals": True}
