"""Smoke tests for the ProxyFix configuration: post-deploy through the real proxy chain, and against docker compose in
CI.

They call /healthcheck/client and prove that the app resolves the caller's address, uses the public scheme and the
canonical host, sees exactly the number of X-Forwarded-For entries its PROXY_FIX_FOR config expects, and that none of
this can be spoofed by request headers. They use plain `requests` and need no browser, database or AWS access.

Against docker compose the app runs under `flask run` with no proxy in front and PROXY_FIX_* all 0, so ProxyFix is not
in the request path: that run only proves the /healthcheck/client contract and that this suite still works before a
deploy depends on it. The post-deploy run in deploy.yml is the one that exercises CloudFront, the ALB and ProxyFix
together.

Run locally against docker compose:

    uv run pytest tests/smoke --confcutdir=tests/smoke --smoke-env local

`--confcutdir=tests/smoke` stops pytest loading the root tests/conftest.py, which imports the whole app, so the smoke
run needs only `requests` and none of the app's configuration or services.
"""

import warnings
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any

import pytest
import requests
from _pytest.config.argparsing import Parser
from urllib3.exceptions import InsecureRequestWarning


@dataclass(frozen=True)
class SmokeEnvironment:
    base_url: str
    verify_tls: bool
    caller_is_public: bool


CLIENT_PATH = "/healthcheck/client"

SMOKE_ENVIRONMENTS = {
    "local": SmokeEnvironment(
        "https://funding.communities.gov.localhost:8080", verify_tls=False, caller_is_public=False
    ),
    "dev": SmokeEnvironment("https://funding.dev.communities.gov.uk", verify_tls=True, caller_is_public=True),
    "test": SmokeEnvironment("https://funding.test.communities.gov.uk", verify_tls=True, caller_is_public=True),
    "prod": SmokeEnvironment("https://funding.communities.gov.uk", verify_tls=True, caller_is_public=True),
}

SmokeGet = Callable[..., requests.Response]


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("smoke", "Smoke tests (tests/smoke)")
    group.addoption("--smoke-env", choices=list(SMOKE_ENVIRONMENTS), default=None, help="the environment to test")


@pytest.fixture(scope="session")
def smoke_env(request: pytest.FixtureRequest) -> SmokeEnvironment:
    env_name = request.config.getoption("smoke_env", default=None)
    if env_name is None:
        pytest.skip("smoke tests only run with --smoke-env")
    return SMOKE_ENVIRONMENTS[env_name]


@pytest.fixture(scope="session")
def smoke_get(smoke_env: SmokeEnvironment) -> Generator[SmokeGet, None, None]:
    with requests.Session() as session:

        def get(path: str, headers: dict[str, str] | None = None) -> requests.Response:
            with warnings.catch_warnings():
                if not smoke_env.verify_tls:
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                return session.get(
                    smoke_env.base_url + path,
                    headers=headers,
                    allow_redirects=False,
                    timeout=10,
                    verify=smoke_env.verify_tls,
                )

        yield get


@pytest.fixture(scope="session")
def baseline(smoke_get: SmokeGet) -> dict[str, Any]:
    response = smoke_get(CLIENT_PATH)
    assert response.status_code == 200, response.text
    return response.json()
