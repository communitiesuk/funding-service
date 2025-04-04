from dataclasses import dataclass
from typing import Generator

import pytest


@dataclass
class FundingServiceDomains:
    landing_url: str


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
def domains(request: pytest.FixtureRequest, get_e2e_params: dict[str, str]) -> FundingServiceDomains:
    e2e_env = get_e2e_params["e2e_env"]

    if e2e_env == "local":
        return FundingServiceDomains(
            landing_url="https://funding.communities.gov.localhost:8080",
        )
    else:
        raise ValueError(f"not configured for {e2e_env}")
