from app.deliver_grant_funding.routes.collections import _build_upload_data_set_preview_data


class TestBuildDataSetPreviewData:
    def test_three_rows_three_previews(self):
        result = _build_upload_data_set_preview_data(
            ["col1", "col2"],
            [
                {"col1": "aaa", "col2": "bbb", "col3": "ccc"},
                {"col1": "ddd", "col2": "eee", "col3": "fff"},
                {"col1": "ggg", "col2": "hhh", "col3": "iii"},
            ],
        )
        assert result == {"col1": ["aaa", "ddd", "ggg"], "col2": ["bbb", "eee", "hhh"]}

    def test_three_rows_some_blanks(self):
        result = _build_upload_data_set_preview_data(
            ["col1", "col2"],
            [
                {"col1": "aaa", "col2": "", "col3": "ccc"},
                {"col1": "", "col2": "eee", "col3": "fff"},
                {"col1": "ggg", "col2": "hhh", "col3": "iii"},
            ],
        )
        assert result == {"col1": ["aaa", "ggg"], "col2": ["eee", "hhh"]}

    def test_more_than_three_rows_some_blanks_in_first_three(self):
        result = _build_upload_data_set_preview_data(
            ["col1", "col2"],
            [
                {"col1": "aaa", "col2": "", "col3": "ccc"},
                {"col1": "", "col2": "eee", "col3": "fff"},
                {"col1": "ggg", "col2": "hhh", "col3": "iii"},
                {"col1": "jjj", "col2": "kkk", "col3": "lll"},
            ],
        )
        assert result == {"col1": ["aaa", "ggg", "jjj"], "col2": ["eee", "hhh", "kkk"]}
