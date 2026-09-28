import pytest
from bs4 import BeautifulSoup
from flask import render_template_string
from pydantic import ValidationError

from app.common.helpers.pagination import Pagination
from tests.utils import get_link_hrefs, page_has_link


def _page_url(page: int) -> str:
    return f"/results?page={page}"


def _item_sequence(params):
    return ["…" if item.get("ellipsis") else item["number"] for item in params["items"]]


class TestPagination:
    @pytest.mark.parametrize(
        "page, total_pages",
        [
            pytest.param(3, 2, id="page past the end"),
            pytest.param(0, 1, id="zero page"),
            pytest.param(1, 0, id="zero total"),
            pytest.param("1", 1, id="string page"),
        ],
    )
    def test_rejects_pages_outside_a_positive_range(self, page, total_pages):
        with pytest.raises(ValidationError):
            Pagination(page=page, total_pages=total_pages)

    class TestFromCounts:
        @pytest.mark.parametrize(
            "total_items, items_per_page, page, max_pages, expected_page, expected_total_pages",
            [
                pytest.param(21, 20, 1, None, 1, 2, id="rounds up a partial page"),
                pytest.param(40, 20, 1, None, 1, 2, id="exact multiple"),
                pytest.param(0, 20, 1, None, 1, 1, id="no items still has one page"),
                pytest.param(5000, 20, 1, 50, 1, 50, id="capped total pages"),
                pytest.param(45, 20, 2, None, 2, 3, id="keeps a middle page"),
                pytest.param(45, 20, 3, None, 3, 3, id="keeps the last page"),
                pytest.param(45, 20, 4, None, 1, 3, id="page past the end falls back"),
                pytest.param(45, 20, 0, None, 1, 3, id="zero page falls back"),
                pytest.param(45, 20, -1, None, 1, 3, id="negative page falls back"),
                pytest.param(5000, 20, 51, 50, 1, 50, id="page past the cap falls back"),
            ],
        )
        def test_derives_the_page_and_total_pages(
            self, total_items, items_per_page, page, max_pages, expected_page, expected_total_pages
        ):
            pagination = Pagination.from_counts(total_items, items_per_page, page=page, max_pages=max_pages)

            assert pagination == Pagination(page=expected_page, total_pages=expected_total_pages)

        @pytest.mark.parametrize(
            "total_items, items_per_page, max_pages",
            [
                pytest.param(-1, 20, None, id="negative items"),
                pytest.param(10, 0, None, id="zero page size"),
                pytest.param(10, 20, 0, id="zero cap"),
            ],
        )
        def test_rejects_impossible_counts(self, total_items, items_per_page, max_pages):
            with pytest.raises(ValueError):
                Pagination.from_counts(total_items, items_per_page, max_pages=max_pages)

    class TestToGovukPagination:
        def test_a_single_page_needs_no_component(self, mocker):
            page_url = mocker.Mock()

            assert Pagination(page=1, total_pages=1).to_govuk_pagination(page_url) is None
            page_url.assert_not_called()

        @pytest.mark.parametrize(
            "page, total_pages, expected_sequence",
            [
                pytest.param(5, 10, ["1", "…", "4", "5", "6", "…", "10"], id="ellipses either side"),
                pytest.param(4, 10, ["1", "2", "3", "4", "5", "…", "10"], id="single gap is filled"),
                pytest.param(7, 10, ["1", "…", "6", "7", "8", "9", "10"], id="single gap before the end is filled"),
                pytest.param(1, 10, ["1", "2", "…", "10"], id="first page"),
                pytest.param(10, 10, ["1", "…", "9", "10"], id="last page"),
                pytest.param(1, 3, ["1", "2", "3"], id="short run has no ellipses"),
                pytest.param(2, 2, ["1", "2"], id="two pages"),
            ],
        )
        def test_lists_the_first_last_and_neighbouring_pages(self, page, total_pages, expected_sequence):
            params = Pagination(page=page, total_pages=total_pages).to_govuk_pagination(_page_url)

            assert params is not None
            assert _item_sequence(params) == expected_sequence
            assert [item["number"] for item in params["items"] if item.get("current")] == [str(page)]
            assert all(item["href"] == _page_url(int(item["number"])) for item in params["items"] if "number" in item)

        @pytest.mark.parametrize(
            "page, expected_previous, expected_next",
            [
                pytest.param(1, None, _page_url(2), id="first page has only next"),
                pytest.param(2, _page_url(1), _page_url(3), id="middle page has both"),
                pytest.param(3, _page_url(2), None, id="last page has only previous"),
            ],
        )
        def test_links_to_the_previous_and_next_pages_when_they_exist(self, page, expected_previous, expected_next):
            params = Pagination(page=page, total_pages=3).to_govuk_pagination(_page_url)

            assert params is not None
            assert params.get("previous", {}).get("href") == expected_previous
            assert params.get("next", {}).get("href") == expected_next

        def test_renders_with_the_govuk_pagination_macro(self):
            params = Pagination(page=5, total_pages=10).to_govuk_pagination(_page_url)
            template = """
            {% from "govuk_frontend_jinja/components/pagination/macro.html" import govukPagination %}
            {{ govukPagination(params) }}
            """

            soup = BeautifulSoup(render_template_string(template, params=params), "html.parser")

            current_page_link = page_has_link(soup, "5")
            assert current_page_link is not None
            assert current_page_link.attrs["aria-current"] == "page"
            assert page_has_link(soup, "Previous").attrs["href"] == _page_url(4)
            assert page_has_link(soup, "Next").attrs["href"] == _page_url(6)
            assert get_link_hrefs(soup) == [_page_url(page) for page in (4, 1, 4, 5, 6, 10, 6)]
            assert "⋯" in soup.text
