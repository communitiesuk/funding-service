import math
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import quote, urlencode

import requests
from cachetools import TTLCache
from flask import Flask, current_app
from pydantic import BaseModel, Field, ValidationError

_REQUEST_TIMEOUT_SECONDS = 5
_SEARCH_ITEMS_PER_PAGE = 20
_CACHE_MAXSIZE = 1000


class CompaniesHouseError(Exception):
    def __init__(self, message: str = "There was a problem looking up the Companies House register"):
        self.message = message
        super().__init__(self.message)


class CompaniesHouseNotFoundError(CompaniesHouseError):
    def __init__(self, message: str = "The company was not found on the Companies House register"):
        super().__init__(message)


class CompanySearchResult(BaseModel):
    company_number: str
    title: str
    address_snippet: str | None = None
    company_status: str | None = None


class CompanySearchResults(BaseModel):
    items: list[CompanySearchResult] = Field(default_factory=list)
    total_results: int = 0
    start_index: int = 0
    items_per_page: int = _SEARCH_ITEMS_PER_PAGE

    @property
    def page(self) -> int:
        return self.start_index // self.items_per_page + 1

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total_results / self.items_per_page))


class CompanyProfile(BaseModel):
    company_number: str
    company_name: str
    company_status: str | None = None


class PCompaniesHouseCache(Protocol):
    """A cache of raw Companies House JSON responses, keyed by the request that produced them.

    Values are plain JSON-serialisable dicts so that a backend shared between processes (for example redis) can store
    them unchanged.
    """

    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any]) -> None: ...

    def clear(self) -> None: ...


class InMemoryCompaniesHouseCache:
    """A per-process cache that expires entries after a fixed time; the backend until a shared cache is available."""

    def __init__(self, *, maxsize: int, ttl_seconds: int, timer: Callable[[], float] = time.monotonic) -> None:
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds, timer=timer)

    def get(self, key: str) -> dict[str, Any] | None:
        return self._cache.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()


class CompaniesHouseService:
    """Looks companies up on the Companies House public data API.

    https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference
    """

    def init_app(self, app: Flask) -> None:
        app.extensions["companies_house_service"] = self
        self.cache: PCompaniesHouseCache = InMemoryCompaniesHouseCache(
            maxsize=_CACHE_MAXSIZE, ttl_seconds=app.config["COMPANIES_HOUSE_CACHE_TTL_SECONDS"]
        )
        self._http = requests.Session()
        # Companies House authenticates with HTTP basic auth, using the API key as the username and no password.
        self._http.auth = (app.config["COMPANIES_HOUSE_API_KEY"], "")

    def search_companies(self, query: str, page: int = 1) -> CompanySearchResults:
        data = self._get_json(
            "/search/companies",
            {
                "q": query,
                "items_per_page": _SEARCH_ITEMS_PER_PAGE,
                "start_index": (max(page, 1) - 1) * _SEARCH_ITEMS_PER_PAGE,
            },
        )
        return self._parse(CompanySearchResults, data)

    def get_company(self, company_number: str) -> CompanyProfile:
        data = self._get_json(f"/company/{quote(company_number.strip().upper(), safe='')}")
        return self._parse(CompanyProfile, data)

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if current_app.config["COMPANIES_HOUSE_DISABLE"]:
            current_app.logger.info(
                "Companies House service is disabled. Would have requested %(path)s", dict(path=path)
            )
            raise CompaniesHouseError()

        cache_key = f"{path}?{urlencode(sorted((params or {}).items()))}"
        if (cached := self.cache.get(cache_key)) is not None:
            return cached

        try:
            response = self._http.get(
                current_app.config["COMPANIES_HOUSE_API_URL"] + path, params=params, timeout=_REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as e:
            current_app.logger.warning("Companies House request failed for %(path)s", dict(path=path))
            raise CompaniesHouseError() from e

        if response.status_code == 404:
            raise CompaniesHouseNotFoundError()
        if not response.ok:
            current_app.logger.warning(
                "Companies House returned %(status_code)s for %(path)s",
                dict(status_code=response.status_code, path=path),
            )
            raise CompaniesHouseError()

        try:
            data = response.json()
        except ValueError as e:
            raise CompaniesHouseError() from e

        self.cache.set(cache_key, data)
        return data

    @staticmethod
    def _parse[T: BaseModel](model: type[T], data: dict[str, Any]) -> T:
        try:
            return model.model_validate(data)
        except ValidationError as e:
            current_app.logger.exception(
                "Companies House returned an unexpected %(model)s payload", dict(model=model.__name__)
            )
            raise CompaniesHouseError() from e
