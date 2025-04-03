import os
from enum import Enum
from typing import Tuple, Type

from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.types import LogFormats, LogLevels


class Environment(str, Enum):
    UNIT_TEST = "unit_test"
    LOCAL = "local"
    DEV = "dev"
    UAT = "uat"
    PROD = "prod"


class DatabaseSecret(BaseModel):
    username: str
    password: str


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

    def build_database_uri(self) -> PostgresDsn:
        return PostgresDsn(
            url=f"postgresql+psycopg://{self.DATABASE_SECRET.username}:{self.DATABASE_SECRET.password}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    # Flask app
    FLASK_ENV: Environment
    SERVER_NAME: str
    SECRET_KEY: str
    WTF_CSRF_ENABLED: bool = True

    # Databases
    DATABASE_HOST: str
    DATABASE_PORT: int
    DATABASE_NAME: str
    DATABASE_SECRET: DatabaseSecret

    @property
    def SQLALCHEMY_ENGINES(self) -> dict[str, str]:
        return {
            "default": str(self.build_database_uri()),
        }

    SQLALCHEMY_RECORD_QUERIES: bool = False

    # Logging
    LOG_LEVEL: LogLevels = "INFO"
    LOG_FORMATTER: LogFormats = "json"

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = False
    DEBUG_TB_INTERCEPT_REDIRECTS: bool = False

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


class UnitTestConfig(LocalConfig):
    """
    Overrides / default configuration for running unit tests.
    """

    # Flask app
    FLASK_ENV: Environment = Environment.UNIT_TEST
    WTF_CSRF_ENABLED: bool = False

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = False


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
        case Environment.UNIT_TEST:
            return UnitTestConfig()  # type: ignore[call-arg]
        case Environment.LOCAL:
            return LocalConfig()  # type: ignore[call-arg]
        case Environment.DEV:
            return DevConfig()  # type: ignore[call-arg]
        case Environment.UAT:
            return UatConfig()  # type: ignore[call-arg]
        case Environment.PROD:
            return ProdConfig()  # type: ignore[call-arg]

    raise ValueError(f"Unknown environment: {environment}")
