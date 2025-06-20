import pytest

from app.common.filters import to_ordinal


class TestToOrdinal:
    @pytest.mark.parametrize(
        "number, ordinal",
        (
            (1, "first"),
            (2, "second"),
            (3, "third"),
            (10, "tenth"),
            (11, "eleventh"),
            (12, "twelfth"),
            (13, "thirteenth"),
            (14, "fourteenth"),
            (21, "twenty-first"),
        ),
    )
    def test_number_to_ordinal(self, number, ordinal):
        assert to_ordinal(number) == ordinal
