import pytest

from app.deliver_grant_funding.data_sets import CSVDecodeError, decode_csv_bytes


class TestDecodeCsvBytes:
    def test_decodes_utf8_sig(self):
        content = "Organisation ID,Grant recipient\nT01,Zürich"
        assert decode_csv_bytes(content.encode("utf-8-sig")) == content

    def test_decodes_plain_utf8(self):
        content = "Organisation ID,Grant recipient\nT01,Zürich"
        assert decode_csv_bytes(content.encode("utf-8")) == content

    def test_decodes_cp1252_excel_export(self):
        # eg a CSV saved from Excel/Windows via "CSV (Comma delimited)" rather than "CSV UTF-8"
        content = "Organisation ID,Grant recipient\nT01,Zürich Café münchen"
        assert decode_csv_bytes(content.encode("cp1252")) == content

    def test_raises_for_unreadable_binary(self):
        with pytest.raises(CSVDecodeError):
            decode_csv_bytes(bytes([0x00, 0x01, 0x02, 0xFF, 0xFE, 0xFD, 0x80, 0x81, 0x00, 0x00]))
