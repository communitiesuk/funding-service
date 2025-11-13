from app import CollectionStatusEnum


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
