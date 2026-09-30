import pytest

from app.common.helpers.charities import normalise_charity_number


class TestNormaliseCharityNumber:
    @pytest.mark.parametrize(
        "charity_number, expected",
        [
            ("123456", "123456"),
            (" 123 4567 ", "1234567"),
            ("1234\t567", "1234567"),
            ("sc 012345", "SC012345"),
            ("SCO12345", "SC012345"),
            ("nic 123456", "NIC123456"),
        ],
    )
    def test_returns_the_number_as_written_on_its_register(self, charity_number, expected):
        assert normalise_charity_number(charity_number) == expected

    @pytest.mark.parametrize(
        "charity_number",
        ["12345", "12345678", "1234567-1", "１２３４５６７", "SC12345", "SC0１２３４５", "NIC12345", "CC-1234567"],
    )
    def test_rejects_a_number_in_no_registers_format(self, charity_number):
        with pytest.raises(ValueError, match="Charity number must be 6 or 7 digits"):
            normalise_charity_number(charity_number)
