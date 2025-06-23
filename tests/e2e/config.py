import json
import re
import subprocess
from typing import Literal, Protocol, cast
from uuid import UUID

import boto3
from playwright.sync_api import HttpCredentials


class EndToEndTestSecrets(Protocol):
    @property
    def HTTP_BASIC_AUTH(self) -> HttpCredentials | None: ...

    @property
    def GOVUK_NOTIFY_API_KEY(self) -> str: ...

    @property
    def SECRET_KEY(self) -> str: ...

    @property
    def SSO_USER_ID(self) -> UUID: ...


class LocalEndToEndSecrets:
    @property
    def HTTP_BASIC_AUTH(self) -> None:
        return None

    @property
    def GOVUK_NOTIFY_API_KEY(self) -> str:
        with open(".env") as env_file:
            notify_key_line = re.search(r"^GOVUK_NOTIFY_API_KEY=(.+)$", env_file.read(), flags=re.MULTILINE)
            if not notify_key_line:
                raise ValueError("Could not read GOV.UK Notify API key from local .env file")

            return notify_key_line.group(1)

    @property
    def SECRET_KEY(self) -> str:
        with open(".env") as env_file:
            secret_key_line = re.search(r"^SECRET_KEY=(.+)$", env_file.read(), flags=re.MULTILINE)
            if not secret_key_line:
                raise ValueError("Could not read SECRET KEY from local .env file")

            return secret_key_line.group(1)

    @property
    def SSO_USER_ID(self) -> UUID:
        with open(".env") as env_file:
            sso_user_id_line = re.search(r"^SSO_USER_ID=(.+)$", env_file.read(), flags=re.MULTILINE)
            if not sso_user_id_line:
                raise ValueError("Could not read SSO user ID from local .env file")

            return cast(UUID, sso_user_id_line.group(1))


class AWSEndToEndSecrets:
    def __init__(self, e2e_env: Literal["dev", "test"], e2e_aws_vault_profile: str | None):
        self.e2e_env = e2e_env
        self.e2e_aws_vault_profile = e2e_aws_vault_profile

        if self.e2e_env == "prod":  # type: ignore[comparison-overlap]
            # It shouldn't be possible to set e2e_env to `prod` based on current setup; this is a safeguard against it
            # being added in the future without thinking about this fixture. When it comes to prod secrets, remember:
            #   keep it secret; keep it safe.
            raise ValueError("Refusing to init against prod environment because it would read production secrets")

    def _read_aws_parameter_store_value(self, parameter: str) -> str:
        # This flow is used to collect secrets when running tests *from* your local machine
        if self.e2e_aws_vault_profile:
            value = json.loads(
                subprocess.check_output(
                    [
                        "aws-vault",
                        "exec",
                        self.e2e_aws_vault_profile,
                        "--",
                        "aws",
                        "ssm",
                        "get-parameter",
                        "--name",
                        parameter,
                        "--with-decryption",
                    ],
                ).decode()
            )["Parameter"]["Value"]

        # This flow is used when running tests *in* CI/CD, where AWS credentials are available from OIDC auth
        else:
            ssm_client = boto3.client("ssm")
            value = ssm_client.get_parameter(Name=parameter, WithDecryption=True)["Parameter"]["Value"]

        return cast(str, value)

    @property
    def HTTP_BASIC_AUTH(self) -> HttpCredentials:
        return {
            "username": self._read_aws_parameter_store_value("/apprunner/funding-service/BASIC_AUTH_USERNAME"),
            "password": self._read_aws_parameter_store_value("/apprunner/funding-service/BASIC_AUTH_PASSWORD"),
        }

    @property
    def GOVUK_NOTIFY_API_KEY(self) -> str:
        return self._read_aws_parameter_store_value("/apprunner/funding-service/GOVUK_NOTIFY_API_KEY")

    @property
    def SECRET_KEY(self) -> str:
        return self._read_aws_parameter_store_value("/apprunner/funding-service/SECRET_KEY")

    @property
    def SSO_USER_ID(self) -> UUID:
        return cast(UUID, self._read_aws_parameter_store_value("/apprunner/funding-service/SSO_USER_ID"))
