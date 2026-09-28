from collections.abc import Callable
from itertools import pairwise
from typing import Any, Self

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass


@dataclass(frozen=True, config=ConfigDict(strict=True))
class Pagination:
    """Pagination state and parameters for the GOV.UK pagination macro."""

    page: int = Field(ge=1)
    total_pages: int = Field(ge=1)

    def __post_init__(self) -> None:
        if self.page > self.total_pages:
            raise ValueError("Page must not exceed the total number of pages")

    @classmethod
    def from_counts(cls, total_items: int, items_per_page: int, page: int = 1, max_pages: int | None = None) -> Self:
        if total_items < 0:
            raise ValueError("Total items must not be negative")
        if items_per_page <= 0:
            raise ValueError("Items per page must be positive")
        if max_pages is not None and max_pages <= 0:
            raise ValueError("Maximum pages must be positive")

        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)
        if not 1 <= page <= total_pages:
            page = 1
        return cls(page=page, total_pages=total_pages)

    def to_govuk_pagination(self, page_url: Callable[[int], str]) -> dict[str, Any] | None:
        if self.total_pages == 1:
            return None

        pages = {1, self.total_pages}
        pages.update(range(max(1, self.page - 1), min(self.total_pages, self.page + 1) + 1))
        for before, after in pairwise(sorted(pages)):
            if after - before == 2:
                pages.add(before + 1)

        items: list[dict[str, str | bool]] = []
        previous_page = 0
        for page in sorted(pages):
            if page - previous_page > 1:
                items.append({"ellipsis": True})
            items.append({"number": str(page), "href": page_url(page), "current": page == self.page})
            previous_page = page

        params: dict[str, Any] = {"items": items}
        if self.page > 1:
            params["previous"] = {"href": page_url(self.page - 1)}
        if self.page < self.total_pages:
            params["next"] = {"href": page_url(self.page + 1)}
        return params
