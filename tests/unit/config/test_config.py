import json
import os
from typing import get_type_hints
from unittest.mock import patch

from app.config import DevConfig, LocalConfig, ProdConfig, TestConfig, _SharedConfig
from tests.utils import build_db_config


def test_config_subclasses_do_not_have_conflicting_types() -> None:
    parent_class_types = get_type_hints(_SharedConfig)

    for subclass in [LocalConfig, DevConfig, TestConfig, ProdConfig]:
        subclass_types = get_type_hints(subclass)

        for attr_name, attr_type in parent_class_types.items():
            assert parent_class_types[attr_name] == subclass_types[attr_name], (
                f"SharedConfig defines {attr_name} as type `{attr_type}` "
                f"but {subclass.__name__} defines it as type `{subclass_types[attr_name]}`"
            )


def test_config_subclasses_do_not_define_new_variables() -> None:
    parent_class_types = get_type_hints(_SharedConfig)

    for subclass in [LocalConfig, DevConfig, TestConfig, ProdConfig]:
        subclass_types = get_type_hints(subclass)

        for attr_name in subclass_types.keys():
            assert attr_name in parent_class_types, (
                f"SharedConfig does not define an {attr_name} config variable, but it is present on {subclass.__name__}"
            )


def test_deployed_config_reads_internal_domains_from_environment() -> None:
    env = {
        **build_db_config(None),
        "SECRET_KEY": "test-secret",  # pragma: allowlist secret
        "SERVER_NAME": "funding.communities.gov.uk",
        "AWS_S3_BUCKET_NAME": "test-bucket",
        "GOVUK_NOTIFY_API_KEY": "test-notify-key",  # pragma: allowlist secret
        "GOVUK_NOTIFY_CALLBACK_TOKEN": "test-callback-token",  # pragma: allowlist secret
        "AZURE_AD_CLIENT_ID": "test-client-id",
        "AZURE_AD_CLIENT_SECRET": "test-client-secret",  # pragma: allowlist secret
        "AZURE_AD_TENANT_ID": "test-tenant-id",
        "JIRA_DATA_CONNECTOR_API_TOKEN": "test-jira-token",  # pragma: allowlist secret
        "INTERNAL_DOMAINS": json.dumps(["@communities.gov.uk", "@example.com"]),
    }

    with patch.dict(os.environ, env, clear=True):
        config = ProdConfig()

    assert config.INTERNAL_DOMAINS == ("@communities.gov.uk", "@example.com")
