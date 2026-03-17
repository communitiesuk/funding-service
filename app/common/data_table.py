from __future__ import annotations

import dataclasses
from typing import Any, Callable
from urllib.parse import urlencode, urlparse, urlunparse

from flask_admin.contrib.sqla.filters import BaseSQLAFilter
from flask_admin.model.filters import BaseFilter
from werkzeug.datastructures import MultiDict


class SelectFilter(BaseFilter):
    """A select filter for fields that are not backed by a DB column (e.g. computed properties).

    Provides options for UI rendering. Skipped by DataTable.apply_filters() since it is
    not a BaseSQLAFilter — the caller must filter data before passing it to DataTable.
    """

    def apply(self, query: Any, value: Any) -> Any:
        raise NotImplementedError("SelectFilter is not applicable to a SQLAlchemy query")

    def operation(self) -> str:
        return "equals"


@dataclasses.dataclass
class Cell:
    value: Any
    html: str
    is_html: bool


@dataclasses.dataclass
class Row:
    cells: list[Cell]
    data: Any  # reference to original data item


@dataclasses.dataclass
class ActiveFilter:
    label: str
    value: str
    display_value: str
    remove_url: str


class Column:
    def __init__(
        self,
        label: str,
        accessor: str,
        *,
        sortable: bool = False,
        filter: BaseFilter | None = None,
        formatter: Callable[[Any, Any], str] | None = None,
        link: Callable[[Any], str] | None = None,
        is_html: bool = False,
        classes: str = "",
    ):
        self.label = label
        self.accessor = accessor
        self.sortable = sortable
        self.filter = filter
        self.formatter = formatter
        self.link = link
        self.is_html = is_html or link is not None
        self.classes = classes

        # Set by DataTable after construction
        self.sort_url: str = ""
        self.is_sorted: bool = False
        self.sort_direction: str = ""  # "asc" or "desc" when sorted


class DataTable:
    def __init__(
        self,
        columns: list[Column],
        data: list[Any] | None = None,
        request_args: MultiDict | dict | None = None,
        current_url: str = "",
    ):
        self._columns = columns
        self._request_args = MultiDict(request_args) if request_args else MultiDict()
        self._current_url = current_url

        self._sort_col: str | None = None
        self._sort_dir: str = "asc"
        self._filter_values: dict[str, str] = {}

        self._rows: list[Row] = []
        self._data_count: int = 0

        self._parse_params()
        self._apply_column_sort_state()

        if data is not None:
            self.set_data(data)

    def set_data(self, data: list[Any]) -> None:
        """Set or replace the table data, building rows after sorting."""
        data = self.filter_data(data)
        self._data_count = len(data)
        sorted_data = self._apply_sort(data)
        self._rows = self._build_rows(sorted_data)

    def apply_filters(self, query: Any) -> Any:
        """Apply active SQLA filters to a SQLAlchemy query and return the modified query."""
        col_map = {c.accessor: c for c in self._columns if c.filter}
        for accessor, value in self._filter_values.items():
            col = col_map.get(accessor)
            if col and isinstance(col.filter, BaseSQLAFilter):
                cleaned = col.filter.clean(value)
                query = col.filter.apply(query, cleaned)
        return query

    def filter_data(self, data: list[Any]) -> list[Any]:
        """Apply active non-SQLA filters to a list of data in memory.

        Filters with options use exact match; text filters use case-insensitive substring match.
        SQLA filters are skipped (use apply_filters for those).
        """
        col_map = {c.accessor: c for c in self._columns if c.filter}
        for accessor, value in self._filter_values.items():
            col = col_map.get(accessor)
            if not col or isinstance(col.filter, BaseSQLAFilter):
                continue
            if col.filter.options:
                data = [item for item in data if str(self._get_value(item, accessor)) == value]
            else:
                data = [item for item in data if value.lower() in str(self._get_value(item, accessor) or "").lower()]
        return data

    def _parse_params(self) -> None:
        self._sort_col = self._request_args.get("sort", None)
        self._sort_dir = self._request_args.get("sort_dir", "asc")
        if self._sort_dir not in ("asc", "desc"):
            self._sort_dir = "asc"

        filterable_accessors = {c.accessor for c in self._columns if c.filter}
        for key, value in self._request_args.items():
            if key.startswith("flt_"):
                accessor = key[4:]
                if accessor in filterable_accessors and value:
                    self._filter_values[accessor] = value

    def _apply_column_sort_state(self) -> None:
        for col in self._columns:
            if not col.sortable:
                continue

            if col.accessor == self._sort_col:
                col.is_sorted = True
                col.sort_direction = self._sort_dir
                toggled = "desc" if self._sort_dir == "asc" else "asc"
                col.sort_url = self._build_url(sort=col.accessor, sort_dir=toggled)
            else:
                col.is_sorted = False
                col.sort_direction = ""
                col.sort_url = self._build_url(sort=col.accessor, sort_dir="asc")

    def _get_value(self, item: Any, accessor: str) -> Any:
        if isinstance(item, dict):
            return item.get(accessor)
        return getattr(item, accessor, None)

    def _apply_sort(self, data: list[Any]) -> list[Any]:
        if not self._sort_col:
            return data

        col_map = {c.accessor: c for c in self._columns}
        col = col_map.get(self._sort_col)
        if not col or not col.sortable:
            return data

        def sort_key(item: Any) -> Any:
            val = self._get_value(item, self._sort_col)  # type: ignore
            if val is None:
                return ""
            return val

        return sorted(data, key=sort_key, reverse=(self._sort_dir == "desc"))

    def _build_rows(self, data: list[Any]) -> list[Row]:
        rows = []
        for item in data:
            cells = []
            for col in self._columns:
                raw_value = self._get_value(item, col.accessor)

                if col.formatter:
                    display = col.formatter(raw_value, item)
                else:
                    display = raw_value if raw_value is not None else ""

                is_html = col.is_html
                html = str(display)

                if col.link:
                    href = col.link(item)
                    if href:
                        html = f'<a class="govuk-link govuk-link--no-visited-state" href="{href}">{display}</a>'
                        is_html = True

                cells.append(Cell(value=raw_value, html=html, is_html=is_html))
            rows.append(Row(cells=cells, data=item))
        return rows

    def _build_url(self, **overrides: str) -> str:
        params: dict[str, str] = {}
        # Preserve filter params
        for key, value in self._request_args.items():
            if key.startswith("flt_"):
                params[key] = value
        # Apply sort params
        params["sort"] = overrides.get("sort", self._sort_col or "")
        params["sort_dir"] = overrides.get("sort_dir", self._sort_dir)
        # Apply filter overrides
        for key, value in overrides.items():
            if key.startswith("flt_"):
                params[key] = value
        # Remove empty values
        params = {k: v for k, v in params.items() if v}

        if self._current_url:
            parsed = urlparse(self._current_url)
            return urlunparse(parsed._replace(query=urlencode(params)))
        return "?" + urlencode(params)

    def _remove_filter_url(self, accessor: str) -> str:
        params: dict[str, str] = {}
        for key, value in self._request_args.items():
            if key == f"flt_{accessor}":
                continue
            if key.startswith("flt_") or key in ("sort", "sort_dir"):
                params[key] = value

        if self._current_url:
            parsed = urlparse(self._current_url)
            return urlunparse(parsed._replace(query=urlencode(params)))
        return "?" + urlencode(params) if params else "?"

    @property
    def columns(self) -> list[Column]:
        return self._columns

    @property
    def rows(self) -> list[Row]:
        return self._rows

    @property
    def has_filters(self) -> bool:
        return any(c.filter for c in self._columns)

    @property
    def active_filters(self) -> list[ActiveFilter]:
        result = []
        col_map = {c.accessor: c for c in self._columns}
        for accessor, value in self._filter_values.items():
            col = col_map.get(accessor)
            if not col or not col.filter:
                continue

            display_value = value
            if col.filter.options:
                for choice_val, choice_label in col.filter.options:
                    if choice_val == value:
                        display_value = choice_label
                        break

            result.append(
                ActiveFilter(
                    label=col.label,
                    value=value,
                    display_value=display_value,
                    remove_url=self._remove_filter_url(accessor),
                )
            )
        return result

    @property
    def filter_columns(self) -> list[Column]:
        return [c for c in self._columns if c.filter]

    @property
    def filter_values(self) -> dict[str, str]:
        return dict(self._filter_values)

    @property
    def clear_filters_url(self) -> str:
        params = {}
        for key, value in self._request_args.items():
            if key in ("sort", "sort_dir"):
                params[key] = value
        if self._current_url:
            parsed = urlparse(self._current_url)
            return urlunparse(parsed._replace(query=urlencode(params)))
        return "?" + urlencode(params) if params else "?"

    @property
    def empty(self) -> bool:
        return len(self._rows) == 0

    @property
    def total_count(self) -> int:
        return self._data_count

    @property
    def filtered_count(self) -> int:
        return self._data_count
