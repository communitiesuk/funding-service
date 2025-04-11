from typing import Generator

import pytest
from playwright.sync_api import Page
from pytest import FixtureRequest


@pytest.fixture(autouse=True)
def _viewport(request: FixtureRequest, page: Page) -> None:
    width, height = request.config.getoption("viewport").split("x")
    page.set_viewport_size({"width": int(width), "height": int(height)})


@pytest.fixture
def get_e2e_params(request: pytest.FixtureRequest) -> Generator[dict[str, str], None, None]:
    e2e_env = request.config.getoption("e2e_env", "local")
    # vault_profile = request.config.getoption("e2e_aws_vault_profile", None)
    # session_token_from_env = os.getenv("AWS_SESSION_TOKEN", None)
    # if not session_token_from_env and e2e_env != "local" and not vault_profile:
    #     sys.exit("Must supply e2e-aws-vault-profile with e2e-env")
    yield {
        "e2e_env": e2e_env,
        # "e2e_aws_vault_profile": vault_profile,
    }


@pytest.fixture()
def domain(request: pytest.FixtureRequest, get_e2e_params: dict[str, str]) -> str:
    e2e_env = get_e2e_params["e2e_env"]

    if e2e_env == "local":
        return "https://funding.communities.gov.localhost:8080"
    else:
        raise ValueError(f"not configured for {e2e_env}")
