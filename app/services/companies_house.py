import re
from typing import Annotated, Any, Self
from urllib.parse import quote

import requests
from flask import Flask
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from requests.adapters import HTTPAdapter


def normalize_company_number(company_number: str) -> str:
    company_number = company_number.strip()
    if not re.fullmatch(r"[a-zA-Z0-9]{8}", company_number):
        raise ValueError("Company number must contain eight ASCII letters or digits")
    return company_number.upper()


CompanyNumber = Annotated[str, AfterValidator(normalize_company_number)]
CompanyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CompanySearchResult(BaseModel):
    model_config = ConfigDict(strict=True)

    company_number: CompanyNumber
    title: CompanyName
    address_snippet: str | None = None
    company_status: str | None = None


class CompanySearchResults(BaseModel):
    model_config = ConfigDict(strict=True)

    items: list[CompanySearchResult]
    total_results: int = Field(ge=0)
    items_per_page: int = Field(gt=0)
    start_index: int = Field(ge=0)

    # the most results the service will page through, passed in as validation context by the service
    _max_results: int = PrivateAttr()

    @model_validator(mode="after")
    def validate_paging(self) -> Self:
        if self.start_index % self.items_per_page:
            raise ValueError("Search start index must identify a whole page")
        remaining = max(0, self.total_results - self.start_index)
        if len(self.items) > min(self.items_per_page, remaining) or bool(self.items) != bool(remaining):
            raise ValueError("Search items do not match the paging metadata")
        return self

    @model_validator(mode="after")
    def bind_max_results(self, info: ValidationInfo) -> Self:
        self._max_results = (info.context or {})["max_results"]
        return self

    @property
    def page(self) -> int:
        return self.start_index // self.items_per_page + 1

    @property
    def total_pages(self) -> int:
        count = min(self.total_results, self._max_results)
        total_pages = (count + self.items_per_page - 1) // self.items_per_page
        return max(1, min(self._max_results // self.items_per_page, total_pages))

    @property
    def is_truncated(self) -> bool:
        return self.total_results > self._max_results


class CompanyProfile(BaseModel):
    model_config = ConfigDict(strict=True)

    company_number: CompanyNumber
    company_name: CompanyName
    company_status: str | None = None


class CompaniesHouseError(Exception):
    def __init__(self, reason: str = "upstream", *, status_code: int | None = None) -> None:
        self.reason = reason
        self.status_code = status_code
        super().__init__("There was a problem looking up the Companies House register")


class CompaniesHouseNotFoundError(CompaniesHouseError):
    pass


class CompaniesHouseDisabledError(CompaniesHouseError):
    pass


class CompaniesHouseService:
    """Search and profile lookup using the Companies House public data API."""

    def init_app(self, app: Flask) -> None:
        app.extensions["companies_house_service"] = self
        self.api_url: str = app.config["COMPANIES_HOUSE_API_URL"].rstrip("/")
        self.api_key: str = app.config["COMPANIES_HOUSE_API_KEY"]
        self.disabled: bool = app.config["COMPANIES_HOUSE_DISABLE"]
        self.min_query_length: int = app.config["COMPANIES_HOUSE_MIN_QUERY_LENGTH"]
        self.max_query_length: int = app.config["COMPANIES_HOUSE_MAX_QUERY_LENGTH"]
        self.items_per_page: int = app.config["COMPANIES_HOUSE_SEARCH_ITEMS_PER_PAGE"]
        self.max_search_results: int = app.config["COMPANIES_HOUSE_MAX_SEARCH_RESULTS"]
        self.request_timeout: tuple[float, float] = app.config["COMPANIES_HOUSE_REQUEST_TIMEOUT"]
        self.client = requests.Session()
        self.client.mount("http://", HTTPAdapter(max_retries=0))
        self.client.mount("https://", HTTPAdapter(max_retries=0))

    @property
    def max_search_pages(self) -> int:
        return self.max_search_results // self.items_per_page

    def search_companies(self, query: str, page: int = 1) -> CompanySearchResults:
        query = query.strip()
        if not self.min_query_length <= len(query) <= self.max_query_length:
            raise ValueError(
                f"Query must contain between {self.min_query_length} and {self.max_query_length} characters"
            )
        if not 1 <= page <= self.max_search_pages:
            page = 1
        start_index = (page - 1) * self.items_per_page
        data, status_code = self._get_json(
            "/search/companies", {"q": query, "items_per_page": self.items_per_page, "start_index": start_index}
        )
        results = self._parse(
            CompanySearchResults, data, status_code=status_code, context={"max_results": self.max_search_results}
        )
        if results.items_per_page != self.items_per_page or results.start_index != start_index:
            raise CompaniesHouseError("invalid_payload", status_code=status_code)
        return results

    def get_company(self, company_number: str) -> CompanyProfile:
        company_number = normalize_company_number(company_number)
        data, status_code = self._get_json(f"/company/{quote(company_number, safe='')}")
        profile = self._parse(CompanyProfile, data, status_code=status_code)
        if profile.company_number != company_number:
            raise CompaniesHouseError("invalid_payload", status_code=status_code)
        return profile

    def _get_json(self, path: str, params: dict[str, str | int] | None = None) -> tuple[Any, int]:
        if self.disabled:
            raise CompaniesHouseDisabledError("disabled")
        if not self.api_key.strip():
            raise CompaniesHouseError("configuration")

        status_code = None
        try:
            with self.client.get(
                self.api_url + path,
                params=params,
                auth=(self.api_key, ""),
                timeout=self.request_timeout,
                allow_redirects=False,
            ) as response:
                status_code = response.status_code
                if status_code in (404, 416):
                    raise CompaniesHouseNotFoundError("not_found", status_code=status_code)
                if not 200 <= status_code < 300:
                    raise CompaniesHouseError("upstream", status_code=status_code)
                return response.json(), status_code
        except requests.Timeout as exc:
            raise CompaniesHouseError("timeout", status_code=status_code) from exc
        except requests.exceptions.JSONDecodeError as exc:
            raise CompaniesHouseError("invalid_json", status_code=status_code) from exc
        except requests.RequestException as exc:
            raise CompaniesHouseError("upstream", status_code=status_code) from exc
        except ValueError as exc:
            raise CompaniesHouseError("invalid_json", status_code=status_code) from exc

    @staticmethod
    def _parse[T: BaseModel](
        model: type[T], data: Any, *, status_code: int, context: dict[str, Any] | None = None
    ) -> T:
        try:
            return model.model_validate(data, context=context)
        except ValidationError as exc:
            raise CompaniesHouseError("invalid_payload", status_code=status_code) from exc
