import json
import os
from enum import Enum
from typing import Tuple, Type

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.types import LogFormats, LogLevels


class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    UAT = "uat"
    PROD = "prod"


class _BaseConfig(BaseSettings):
    """
    Stop pydantic-settings from reading configuration from anywhere other than the environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (env_settings,)


class _SharedConfig(_BaseConfig):
    """Shared configuration that is acceptable to be present in all environments (but we'd never expect to instantiate
    this class directly).

    Default configuration values, if provided, should be:
    1. valid and sensible if used in our production environments
    2. acceptable public values, considering they will be in source control

    Anything that does not meet both conditions should not be set as a default value on this base class. Anything
    that does not meet point 1, but does meet point 2, should be set on the appropriate derived class.
    """

    @staticmethod
    def get_database_url() -> PostgresDsn:
        secrets_json = os.environ.get("DATABASE_SECRET", None)

        if secrets_json:
            secrets_dict = json.loads(secrets_json)
            db_host = os.environ.get("DATABASE_HOST", None)
            db_port = os.environ.get("DATABASE_PORT", None)
            db_name = os.environ.get("DATABASE_NAME", None)
            if all([db_host, db_port, db_name, secrets_dict, "username" in secrets_dict, "password" in secrets_dict]):
                return PostgresDsn(
                    url=f"postgresql+psycopg://{secrets_dict['username']}:{secrets_dict['password']}@{db_host}:{db_port}/{db_name}"
                )

        raise ValueError("Database connection string could not be built, values not present in environment")

    # Flask app
    FLASK_ENV: Environment
    SERVER_NAME: str
    SECRET_KEY: str

    # Databases
    DATABASE_URI: PostgresDsn

    @property
    def SQLALCHEMY_ENGINES(self) -> dict[str, str]:
        return {
            "default": str(self.DATABASE_URI),
        }

    SQLALCHEMY_RECORD_QUERIES: bool = False

    # Logging
    LOG_LEVEL: LogLevels = "INFO"
    LOG_FORMATTER: LogFormats = "json"

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = False

    # Flask-Vite
    VITE_AUTO_INSERT: bool = False
    VITE_FOLDER_PATH: str = "app/vite"


class LocalConfig(_SharedConfig):
    """
    Overrides / default configuration for local developer environments.
    """

    FLASK_ENV: Environment = Environment.LOCAL
    SERVER_NAME: str = "funding.communities.gov.localhost:8080"
    SECRET_KEY: str = "unsafe"  # pragma: allowlist secret

    # Databases
    SQLALCHEMY_RECORD_QUERIES: bool = True

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = True

    # Logging
    LOG_FORMATTER: LogFormats = "plaintext"


class DevConfig(_SharedConfig):
    """
    Overrides / default configuration for our deployed 'dev' environment
    """

    FLASK_ENV: Environment = Environment.DEV
    DEBUG_TB_ENABLED: bool = False


class UatConfig(_SharedConfig):
    """
    Overrides / default configuration for our deployed 'uat' environment
    """

    FLASK_ENV: Environment = Environment.UAT


class ProdConfig(_SharedConfig):
    """
    Overrides / default configuration for our deployed 'prod' environment
    """

    FLASK_ENV: Environment = Environment.PROD


def get_settings() -> _SharedConfig:
    environment = os.getenv("FLASK_ENV", Environment.PROD.value)
    match Environment(environment):
        case Environment.LOCAL:
            return LocalConfig()  # type: ignore[call-arg]
        case Environment.DEV:
            return DevConfig(DATABASE_URI=_SharedConfig.get_database_url())  # type: ignore[call-arg]
        case Environment.UAT:
            return UatConfig(DATABASE_URI=_SharedConfig.get_database_url())  # type: ignore[call-arg]
        case Environment.PROD:
            return ProdConfig(DATABASE_URI=_SharedConfig.get_database_url())  # type: ignore[call-arg]

    raise ValueError(f"Unknown environment: {environment}")
