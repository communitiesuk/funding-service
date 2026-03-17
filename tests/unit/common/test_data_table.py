from unittest.mock import MagicMock

from flask_admin.contrib.sqla.filters import FilterLike
from werkzeug.datastructures import MultiDict

from app.common.data_table import Column, DataTable, SelectFilter

SAMPLE_DATA = [
    {"name": "Alpha Corp", "status": "ACTIVE", "score": 90},
    {"name": "Beta Ltd", "status": "INACTIVE", "score": 45},
    {"name": "Gamma Inc", "status": "ACTIVE", "score": 72},
    {"name": "Delta Co", "status": "PENDING", "score": 60},
]


def _make_columns(**overrides):
    mock_column = MagicMock()
    defaults = [
        Column("Name", "name", sortable=True, filter=FilterLike(mock_column, "Name")),
        Column(
            "Status",
            "status",
            sortable=True,
            filter=SelectFilter(
                "Status",
                options=[
                    ("ACTIVE", "Active"),
                    ("INACTIVE", "Inactive"),
                    ("PENDING", "Pending"),
                ],
            ),
        ),
        Column("Score", "score", sortable=True),
    ]
    return defaults


class TestDataTableNoParams:
    def test_rows_match_input_data(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert len(table.rows) == 4

    def test_total_count_equals_data_length(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert table.total_count == 4

    def test_empty_with_no_data(self):
        table = DataTable(columns=_make_columns(), data=[])
        assert table.empty is True

    def test_not_empty_with_data(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert table.empty is False

    def test_has_filters(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert table.has_filters is True

    def test_no_filters_when_columns_have_none(self):
        columns = [Column("Name", "name")]
        table = DataTable(columns=columns, data=SAMPLE_DATA)
        assert table.has_filters is False

    def test_no_active_filters_by_default(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert table.active_filters == []

    def test_cell_values_extracted_from_dicts(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        first_row_cells = table.rows[0].cells
        assert first_row_cells[0].html == "Alpha Corp"
        assert first_row_cells[1].html == "ACTIVE"
        assert first_row_cells[2].html == "90"

    def test_row_data_holds_original_item(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert table.rows[0].data is SAMPLE_DATA[0]


class TestDataTableSorting:
    def test_sort_ascending(self):
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        names = [r.cells[0].html for r in table.rows]
        assert names == ["Alpha Corp", "Beta Ltd", "Delta Co", "Gamma Inc"]

    def test_sort_descending(self):
        args = MultiDict({"sort": "name", "sort_dir": "desc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        names = [r.cells[0].html for r in table.rows]
        assert names == ["Gamma Inc", "Delta Co", "Beta Ltd", "Alpha Corp"]

    def test_sort_numeric(self):
        args = MultiDict({"sort": "score", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        scores = [r.cells[2].value for r in table.rows]
        assert scores == [45, 60, 72, 90]

    def test_sort_invalid_direction_defaults_to_asc(self):
        args = MultiDict({"sort": "score", "sort_dir": "invalid"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        scores = [r.cells[2].value for r in table.rows]
        assert scores == [45, 60, 72, 90]

    def test_sort_non_sortable_column_ignored(self):
        columns = [Column("Name", "name", sortable=False)]
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=columns, data=SAMPLE_DATA, request_args=args)
        names = [r.cells[0].html for r in table.rows]
        assert names == ["Alpha Corp", "Beta Ltd", "Gamma Inc", "Delta Co"]

    def test_sort_unknown_column_ignored(self):
        args = MultiDict({"sort": "nonexistent", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert len(table.rows) == 4

    def test_column_sort_state_set(self):
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        name_col = table.columns[0]
        assert name_col.is_sorted is True
        assert name_col.sort_direction == "asc"

    def test_column_sort_url_toggles_direction(self):
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert "sort_dir=desc" in table.columns[0].sort_url

    def test_unsorted_column_sort_url_is_asc(self):
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        status_col = table.columns[1]
        assert status_col.is_sorted is False
        assert "sort=status" in status_col.sort_url
        assert "sort_dir=asc" in status_col.sort_url

    def test_sort_with_none_values(self):
        data = [
            {"name": "Bravo", "status": "ACTIVE", "score": 10},
            {"name": None, "status": "ACTIVE", "score": 20},
            {"name": "Alpha", "status": "ACTIVE", "score": 30},
        ]
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=data, request_args=args)
        names = [r.cells[0].value for r in table.rows]
        assert names == [None, "Alpha", "Bravo"]


class TestDataTableFilterParsing:
    def test_filter_values_parsed_from_request_args(self):
        args = MultiDict({"flt_name": "alpha", "flt_status": "ACTIVE"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert table.filter_values == {"name": "alpha", "status": "ACTIVE"}

    def test_empty_filter_value_ignored(self):
        args = MultiDict({"flt_name": ""})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert table.filter_values == {}

    def test_unknown_filter_param_ignored(self):
        args = MultiDict({"flt_nonexistent": "test"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert table.filter_values == {}

    def test_filter_and_sort_combined(self):
        args = MultiDict({"flt_status": "ACTIVE", "sort": "score", "sort_dir": "desc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert table.filter_values == {"status": "ACTIVE"}
        scores = [r.cells[2].value for r in table.rows]
        assert scores == [90, 72]


class TestDataTableActiveFilters:
    def test_active_filter_created(self):
        args = MultiDict({"flt_status": "ACTIVE"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert len(table.active_filters) == 1
        af = table.active_filters[0]
        assert af.label == "Status"
        assert af.value == "ACTIVE"
        assert af.display_value == "Active"

    def test_active_filter_text_uses_raw_value(self):
        args = MultiDict({"flt_name": "alpha"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        af = table.active_filters[0]
        assert af.display_value == "alpha"

    def test_remove_url_excludes_filter(self):
        args = MultiDict({"flt_status": "ACTIVE", "sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        af = table.active_filters[0]
        assert "flt_status" not in af.remove_url
        assert "sort=name" in af.remove_url

    def test_clear_filters_url_preserves_sort(self):
        args = MultiDict({"flt_status": "ACTIVE", "flt_name": "a", "sort": "name"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        url = table.clear_filters_url
        assert "flt_" not in url
        assert "sort=name" in url


class TestDataTableFormatters:
    def test_formatter_applied(self):
        columns = [Column("Score", "score", formatter=lambda val, row: f"{val}%")]
        table = DataTable(columns=columns, data=SAMPLE_DATA)
        assert table.rows[0].cells[0].html == "90%"

    def test_link_wraps_in_anchor(self):
        columns = [Column("Name", "name", link=lambda row: f"/items/{row['name']}")]
        table = DataTable(columns=columns, data=SAMPLE_DATA)
        cell = table.rows[0].cells[0]
        assert cell.is_html is True
        assert 'href="/items/Alpha Corp"' in cell.html
        assert "Alpha Corp" in cell.html

    def test_is_html_flag(self):
        columns = [Column("Custom", "name", is_html=True)]
        table = DataTable(columns=columns, data=SAMPLE_DATA)
        assert table.rows[0].cells[0].is_html is True

    def test_none_value_renders_empty(self):
        data = [{"name": None}]
        columns = [Column("Name", "name")]
        table = DataTable(columns=columns, data=data)
        assert table.rows[0].cells[0].html == ""


class TestDataTableObjectAccess:
    def test_getattr_access(self):
        class Item:
            def __init__(self, name):
                self.name = name

        data = [Item("Test")]
        columns = [Column("Name", "name")]
        table = DataTable(columns=columns, data=data)
        assert table.rows[0].cells[0].html == "Test"


class TestDataTableURLBuilding:
    def test_sort_url_preserves_filters(self):
        args = MultiDict({"flt_status": "ACTIVE"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        sort_url = table.columns[0].sort_url
        assert "flt_status=ACTIVE" in sort_url
        assert "sort=name" in sort_url

    def test_current_url_used_as_base(self):
        table = DataTable(
            columns=_make_columns(),
            data=SAMPLE_DATA,
            current_url="/my-page",
        )
        sort_url = table.columns[0].sort_url
        assert sort_url.startswith("/my-page?")


class TestDataTableSetData:
    def test_set_data_builds_rows(self):
        table = DataTable(columns=_make_columns(), request_args={})
        assert table.rows == []
        assert table.total_count == 0

        table.set_data(SAMPLE_DATA)
        assert len(table.rows) == 4
        assert table.total_count == 4

    def test_set_data_applies_sorting(self):
        args = MultiDict({"sort": "name", "sort_dir": "asc"})
        table = DataTable(columns=_make_columns(), request_args=args)
        table.set_data(SAMPLE_DATA)
        names = [r.cells[0].html for r in table.rows]
        assert names == ["Alpha Corp", "Beta Ltd", "Delta Co", "Gamma Inc"]


class TestDataTableApplyFilters:
    def test_apply_filters_calls_sqla_filter(self):
        mock_column = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query

        columns = [
            Column("Name", "name", filter=FilterLike(mock_column, "Name")),
        ]
        args = MultiDict({"flt_name": "alpha"})
        table = DataTable(columns=columns, data=SAMPLE_DATA, request_args=args)

        result = table.apply_filters(mock_query)
        assert result is not None

    def test_apply_filters_skips_non_sqla_filter(self):
        mock_query = MagicMock()

        columns = [
            Column(
                "Status",
                "status",
                filter=SelectFilter("Status", options=[("ACTIVE", "Active")]),
            ),
        ]
        args = MultiDict({"flt_status": "ACTIVE"})
        table = DataTable(columns=columns, data=SAMPLE_DATA, request_args=args)

        result = table.apply_filters(mock_query)
        mock_query.filter.assert_not_called()
        assert result is mock_query

    def test_apply_filters_with_no_active_filters(self):
        mock_query = MagicMock()
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)

        result = table.apply_filters(mock_query)
        mock_query.filter.assert_not_called()
        assert result is mock_query


class TestDataTableFilterData:
    def test_select_filter_exact_match(self):
        args = MultiDict({"flt_status": "ACTIVE"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert len(table.rows) == 2
        statuses = {r.cells[1].html for r in table.rows}
        assert statuses == {"ACTIVE"}

    def test_select_filter_no_match(self):
        args = MultiDict({"flt_status": "UNKNOWN"})
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA, request_args=args)
        assert table.empty is True

    def test_no_active_filters_returns_all_data(self):
        table = DataTable(columns=_make_columns(), data=SAMPLE_DATA)
        assert len(table.rows) == 4
