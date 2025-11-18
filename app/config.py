import copy
import os
import urllib.parse
from enum import Enum
from typing import Any, Self, Tuple

from flask_talisman.talisman import ONE_YEAR_IN_SECS
from pydantic import BaseModel, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.common.data.types import OrganisationType
from app.types import LogFormats, LogLevels


class Environment(str, Enum):
    UNIT_TEST = "unit_test"
    LOCAL = "local"
    PULLPREVIEW = "pullpreview"
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class DatabaseSecret(BaseModel):
    username: str
    password: str


FS_CONTENT_SECURITY_POLICY = {
    "default-src": ["'self'"],
    "content_security_policy_nonce_in": ["script-src"],
    "script-src": [
        "'self'",
        "https://www.googletagmanager.com",
    ],
    "img-src": [
        "'self'",
        "data:",  # Flask-Admin's select-with-search "x" icon for deleting selections
        "www.googletagmanager.com",
    ],
    "style-src": [
        "'self'",
        "'unsafe-hashes'",
        "'sha256-9/aFFbAwf+Mwl6MrBQzrJ/7ZK5vo7HdOUR7iKlBk78U='",  # MHCLG Crest
    ],
    "connect-src": ["'self'", "www.googletagmanager.com", "www.google.com", "https://*.google-analytics.com"],
}


def make_development_csp() -> dict[str, list[str]]:
    csp = copy.deepcopy(FS_CONTENT_SECURITY_POLICY)
    csp["default-src"].extend(
        [
            "http://localhost:5173",  # Vite assets
            "ws://localhost:5173",  # Vite assets
        ]
    )
    csp["script-src"].extend(
        [
            "http://localhost:5173",  # Vite assets
            "ws://localhost:5173",  # Vite assets
            "'sha256-zWl5GfUhAzM8qz2mveQVnvu/VPnCS6QL7Niu6uLmoWU='",  # Flask-DebugToolbar
        ]
    )
    csp["img-src"].extend(
        [
            "http://localhost:5173",  # Vite assets
            "ws://localhost:5173",  # Vite assets
        ]
    )
    csp["style-src"].extend(
        [
            "http://localhost:5173",  # Vite assets
            "ws://localhost:5173",  # Vite assets
            "'sha256-biLFinpqYMtWHmXfkA1BPeCY0/fNt46SAZ+BBk5YUog='",  # Flask-DebugToolbar
            "'sha256-0EZqoz+oBhx7gF4nvY2bSqoGyy4zLjNF+SDQXGp/ZrY='",  # Flask-DebugToolbar
            "'sha256-1NkfmhNaD94k7thbpTCKG0dKnMcxprj9kdSKzKR6K/k='",  # Flask-DebugToolbar
        ]
    )
    return csp


class _BaseConfig(BaseSettings):
    """
    Stop pydantic-settings from reading configuration from anywhere other than the environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
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
        urlsafe_username = urllib.parse.quote(self.DATABASE_SECRET.username)
        urlsafe_password = urllib.parse.quote(self.DATABASE_SECRET.password)
        return PostgresDsn(
            f"postgresql+psycopg://{urlsafe_username}:{urlsafe_password}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    # Flask app
    FLASK_ENV: Environment
    SECRET_KEY: str
    WTF_CSRF_ENABLED: bool = True
    PROXY_FIX_PROTO: int = 1  # CloudFront for AWS environments; Caddy for PullPreview
    PROXY_FIX_HOST: int = 1  # We inject X-Forwarded-For using Cloudfront custom headings
    SERVER_NAME: str

    # Basic auth
    BASIC_AUTH_ENABLED: bool = False
    BASIC_AUTH_USERNAME: str = ""
    BASIC_AUTH_PASSWORD: str = ""

    @model_validator(mode="after")
    def validate_basic_auth_settings(self) -> Self:
        if self.BASIC_AUTH_ENABLED:
            if not self.BASIC_AUTH_USERNAME or not self.BASIC_AUTH_PASSWORD:
                raise ValueError(
                    "BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD must be set if BASIC_AUTH_ENABLED is true."
                )

        return self

    # Talisman security settings
    TALISMAN_FEATURE_POLICY: dict[str, str] = {}
    TALISMAN_PERMISSIONS_POLICY: dict[str, str] = {}
    TALISMAN_DOCUMENT_POLICY: dict[str, str] = {}

    # We can't use this as our deployed healthchecks are over HTTP; we will enforce HTTPS in other ways.
    TALISMAN_FORCE_HTTPS: bool = False
    TALISMAN_FORCE_HTTPS_PERMANENT: bool = False

    TALISMAN_FORCE_FILE_SAVE: bool = False
    TALISMAN_FRAME_OPTIONS: str = "DENY"
    TALISMAN_FRAME_OPTIONS_ALLOW_FROM: str | None = None
    TALISMAN_STRICT_TRANSPORT_SECURITY: bool = True
    TALISMAN_STRICT_TRANSPORT_SECURITY_PRELOAD: bool = True
    TALISMAN_STRICT_TRANSPORT_SECURITY_MAX_AGE: int = ONE_YEAR_IN_SECS
    TALISMAN_STRICT_TRANSPORT_SECURITY_INCLUDE_SUBDOMAINS: bool = True
    TALISMAN_CONTENT_SECURITY_POLICY: dict[str, list[str]] = copy.deepcopy(FS_CONTENT_SECURITY_POLICY)
    TALISMAN_CONTENT_SECURITY_POLICY_REPORT_URI: str | None = None
    TALISMAN_CONTENT_SECURITY_POLICY_REPORT_ONLY: bool = False
    TALISMAN_CONTENT_SECURITY_POLICY_NONCE_IN: list[str] = ["img-src", "script-src", "style-src"]
    TALISMAN_REFERRER_POLICY: str = "strict-origin-when-cross-origin"
    TALISMAN_SESSION_COOKIE_SECURE: bool = True
    TALISMAN_SESSION_COOKIE_HTTP_ONLY: bool = True
    TALISMAN_SESSION_COOKIE_SAMESITE: str = "Lax"
    TALISMAN_X_CONTENT_TYPE_OPTIONS: bool = True
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-XSS-Protection - use CSP instead
    TALISMAN_X_XSS_PROTECTION: bool = False

    @property
    def TALISMAN_SETTINGS(self) -> dict[str, Any]:
        return {
            "feature_policy": self.TALISMAN_FEATURE_POLICY,
            "permissions_policy": self.TALISMAN_PERMISSIONS_POLICY,
            "document_policy": self.TALISMAN_DOCUMENT_POLICY,
            "force_https": self.TALISMAN_FORCE_HTTPS,
            "force_https_permanent": self.TALISMAN_FORCE_HTTPS_PERMANENT,
            "force_file_save": self.TALISMAN_FORCE_FILE_SAVE,
            "frame_options": self.TALISMAN_FRAME_OPTIONS,
            "frame_options_allow_from": self.TALISMAN_FRAME_OPTIONS_ALLOW_FROM,
            "strict_transport_security": self.TALISMAN_STRICT_TRANSPORT_SECURITY,
            "strict_transport_security_preload": self.TALISMAN_STRICT_TRANSPORT_SECURITY_PRELOAD,
            "strict_transport_security_max_age": self.TALISMAN_STRICT_TRANSPORT_SECURITY_MAX_AGE,
            "strict_transport_security_include_subdomains": self.TALISMAN_STRICT_TRANSPORT_SECURITY_INCLUDE_SUBDOMAINS,
            "content_security_policy": self.TALISMAN_CONTENT_SECURITY_POLICY,
            "content_security_policy_report_uri": self.TALISMAN_CONTENT_SECURITY_POLICY_REPORT_URI,
            "content_security_policy_report_only": self.TALISMAN_CONTENT_SECURITY_POLICY_REPORT_ONLY,
            "content_security_policy_nonce_in": self.TALISMAN_CONTENT_SECURITY_POLICY_NONCE_IN,
            "referrer_policy": self.TALISMAN_REFERRER_POLICY,
            "session_cookie_secure": self.TALISMAN_SESSION_COOKIE_SECURE,
            "session_cookie_http_only": self.TALISMAN_SESSION_COOKIE_HTTP_ONLY,
            "session_cookie_samesite": self.TALISMAN_SESSION_COOKIE_SAMESITE,
            "x_content_type_options": self.TALISMAN_X_CONTENT_TYPE_OPTIONS,
            "x_xss_protection": self.TALISMAN_X_XSS_PROTECTION,
        }

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

    RECORD_SQLALCHEMY_QUERIES: bool = False

    # Logging
    LOG_LEVEL: LogLevels = "INFO"
    LOG_FORMATTER: LogFormats = "json"

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = False
    DEBUG_TB_INTERCEPT_REDIRECTS: bool = False
    # We list these explicitly here so that we can disable ConfigVarsDebugPanel in pullpreview environments, where I
    # want another layer of safety against us showing sensitive configuration publicly.
    DEBUG_TB_PANELS: list[str] = [
        "flask_debugtoolbar.panels.versions.VersionDebugPanel",
        "flask_debugtoolbar.panels.timer.TimerDebugPanel",
        "flask_debugtoolbar.panels.headers.HeaderDebugPanel",
        "flask_debugtoolbar.panels.request_vars.RequestVarsDebugPanel",
        "flask_debugtoolbar.panels.config_vars.ConfigVarsDebugPanel",
        "flask_debugtoolbar.panels.template.TemplateDebugPanel",
        "flask_debugtoolbar.panels.sqlalchemy.SQLAlchemyDebugPanel",
        "flask_debugtoolbar.panels.logger.LoggingPanel",
        "flask_debugtoolbar.panels.route_list.RouteListDebugPanel",
        "flask_debugtoolbar.panels.profiler.ProfilerDebugPanel",
        "flask_debugtoolbar.panels.g.GDebugPanel",
    ]

    # GOV.UK Notify
    GOVUK_NOTIFY_DISABLE: bool = False
    GOVUK_NOTIFY_API_KEY: str
    GOVUK_NOTIFY_SERVICE_ID: str = "239747da-5aa1-4fe0-85ab-39d0272ca5c8"  # needs to be kept in sync with the API key
    GOVUK_NOTIFY_MAGIC_LINK_TEMPLATE_ID: str = "9773e73c-85a1-4c3f-a808-02b9623616a3"
    GOVUK_NOTIFY_COLLECTION_SUBMISSION_TEMPLATE_ID: str = "2ff34065-0a75-4cc3-a782-1c00016e526e"
    GOVUK_NOTIFY_MEMBER_CONFIRMATION_TEMPLATE_ID: str = "49ba98c5-0573-4c77-8cb0-3baebe70ee86"
    GOVUK_NOTIFY_DELIVER_ORGANISATION_ADMIN_TEMPLATE_ID: str = "fd143e8b-c735-4e12-9eb5-1655724216d5"
    GOVUK_NOTIFY_DELIVER_ORGANISATION_MEMBER_TEMPLATE_ID: str = "fc85bd85-89bb-4bfc-87af-26e5cdc6cfed"
    GOVUK_NOTIFY_GRANT_RECIPIENT_REPORT_NOTIFICATION_TEMPLATE_ID: str = "4fc8d831-e241-4648-a8d3-04fb1bd9193e"
    GOVUK_NOTIFY_ACCESS_SUBMISSION_SENT_FOR_CERTIFICATION_CONFIRMATION_TEMPLATE_ID: str = (
        "e78b9c68-5d45-40a1-8339-04fe7ffc8caa"
    )
    GOVUK_NOTIFY_ACCESS_SUBMISSION_READY_TO_CERTIFY_TEMPLATE_ID: str = "e511c0d0-2ac8-4ded-80a2-13b79023c5d5"

    ASSETS_VITE_BASE_URL: str = "http://localhost:5173"
    ASSETS_VITE_LIVE_ENABLED: bool = False

    # Azure Active Directory Config
    AZURE_AD_CLIENT_ID: str
    AZURE_AD_CLIENT_SECRET: str
    AZURE_AD_TENANT_ID: str
    AZURE_AD_BASE_URL: str = "https://login.microsoftonline.com/"

    # consumers|organizations|<tenant_id> - signifies the Azure AD tenant endpoint # noqa
    @property
    def AZURE_AD_AUTHORITY(self) -> str:
        return self.AZURE_AD_BASE_URL + self.AZURE_AD_TENANT_ID

    # You can find the proper permission names from this document
    # https://docs.microsoft.com/en-us/graph/permissions-reference
    MS_GRAPH_PERMISSIONS_SCOPE: list[str] = ["User.ReadBasic.All"]

    # Internal Domains
    INTERNAL_DOMAINS: tuple[str, ...] = ("@communities.gov.uk", "@test.communities.gov.uk")

    # Service Desk
    SERVICE_DESK_URL: str = "https://mhclgdigital.atlassian.net/servicedesk/customer/portal/5"
    ACCESS_SERVICE_DESK_URL: str = "https://mhclgdigital.atlassian.net/servicedesk/customer/portal/5/group/1344"
    DELIVER_SERVICE_DESK_URL: str = "https://mhclgdigital.atlassian.net/servicedesk/customer/portal/5/group/1343"
    DELTA_SERVICE_DESK_URL: str = "https://mhclgdigital.atlassian.net/servicedesk/customer/portal/6/group/12"

    # Form rendering options
    ENHANCE_RADIOS_TO_AUTOCOMPLETE_AFTER_X_ITEMS: int = 20

    MAX_DATA_SOURCE_ITEMS_RADIOS: int = 100
    MAX_DATA_SOURCE_ITEMS_CHECKBOXES: int = 10

    # Max number of levels of nested groups
    MAX_NESTED_GROUP_LEVELS: int = 1

    # Grant setup
    GGIS_TEAM_EMAIL: str = "ggis@communities.gov.uk"
    PIPELINE_GRANTS_SCHEME_FORM_URL: str = "https://forms.office.com.mcas.ms/pages/responsepage.aspx?id=EGg0v32c3kOociSi7zmVqBUKhC0CqZtGmIj1YcYa53xUNTFRWkRXQ1ZJUEJMOTg1UllGWEpCNDQ4NSQlQCN0PWcu&route=shorturl"

    PLATFORM_DEPARTMENT_ORGANISATION_CONFIG: dict[str, str] = {
        "name": "Ministry of Housing, Communities and Local Government",
        "external_id": "GB-GOV-27",
        "type": OrganisationType.CENTRAL_GOVERNMENT,
    }
    SEED_SYSTEM_DATA: bool = True
    GRANT_TEAM_RECIPIENT_LIST_SPREADSHEET: str = "https://mhclg.sharepoint.com/:x:/s/FundingServiceOnboarding/EVu_B9_W6OJKvjS8j-Xd_dABBQ0sPGB6vWLNLkoHfrHyHg?e=cG79Bd&nav=MTVfezAwMDAwMDAwLTAwMDEtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMH0"

    # Google Analytics
    GOOGLE_TAG_MANAGER_ID: str = "GTM-T8XPM3NL"

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.FLASK_ENV == Environment.PROD


class LocalConfig(_SharedConfig):
    """
    Overrides / default configuration for local developer environments.
    """

    # Flask app
    FLASK_ENV: Environment = Environment.LOCAL
    SECRET_KEY: str = "unsafe"  # pragma: allowlist secret
    PROXY_FIX_PROTO: int = 0
    PROXY_FIX_HOST: int = 0
    SERVER_NAME: str = "funding.communities.gov.localhost:8080"

    # The LocalConfig needs default values for these AZURE_AD variables so that the Check DB Migrations job
    # can run correctly in CI but these should be overwritten in your local .env file with real values
    # and setting AZURE_AD_BASE_URL to https://login.microsoftonline.com/ if you want to sign in with SSO locally

    # Azure Active Directory Config
    AZURE_AD_CLIENT_ID: str = "00000000-0000-0000-0000-000000000000"
    AZURE_AD_CLIENT_SECRET: str = "incorrect_value"
    AZURE_AD_TENANT_ID: str = "00000000-0000-0000-0000-000000000000"
    AZURE_AD_BASE_URL: str = "https://sso.communities.gov.localhost:4005/"

    # Talisman security settings
    TALISMAN_CONTENT_SECURITY_POLICY: dict[str, list[str]] = make_development_csp()

    # Our `record_sqlalchemy_queries` extension`
    RECORD_SQLALCHEMY_QUERIES: bool = True

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = True

    # Logging
    LOG_FORMATTER: LogFormats = "plaintext"

    # GOV.UK Notify
    GOVUK_NOTIFY_DISABLE: bool = True  # By default; update in .env when you have a key.
    GOVUK_NOTIFY_API_KEY: str = "invalid-00000000-0000-0000-0000-000000000000-00000000-0000-0000-0000-000000000000"

    ASSETS_VITE_LIVE_ENABLED: bool = True


class UnitTestConfig(LocalConfig):
    """
    Overrides / default configuration for running unit tests.
    """

    # Flask app
    FLASK_ENV: Environment = Environment.UNIT_TEST
    WTF_CSRF_ENABLED: bool = False

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED: bool = False

    # GOV.UK Notify
    GOVUK_NOTIFY_DISABLE: bool = False  # We want to test the real code paths

    SEED_SYSTEM_DATA: bool = False


class DevConfig(_SharedConfig):
    """
    Overrides / default configuration for our deployed 'dev' environment
    """

    # Flask app
    FLASK_ENV: Environment = Environment.DEV
    DEBUG_TB_ENABLED: bool = False


class PullPreviewConfig(_SharedConfig):
    """
    Overrides / default configuration for our PR PullPreview environments
    """

    # Flask app
    FLASK_ENV: Environment = Environment.DEV
    DEBUG_TB_ENABLED: bool = False
    PROXY_FIX_PROTO: int = 1
    PROXY_FIX_HOST: int = 1

    # Azure Active Directory Config
    # NB - this won't allow SSO to work yet on pull-previews, but will at least allow pull preview envs to start up
    # correctly and magic link sign-in to be used until we can integrate the SSO stub server to work with pull preview.
    AZURE_AD_CLIENT_ID: str = "00000000-0000-0000-0000-000000000000"
    AZURE_AD_CLIENT_SECRET: str = "incorrect_value"
    AZURE_AD_TENANT_ID: str = "00000000-0000-0000-0000-000000000000"
    AZURE_AD_BASE_URL: str = os.getenv("AZURE_AD_BASE_URL", "https://sso.communities.gov.localhost:4005/")

    # Talisman security settings
    TALISMAN_CONTENT_SECURITY_POLICY: dict[str, list[str]] = make_development_csp()


class TestConfig(_SharedConfig):
    """
    Overrides / default configuration for our deployed 'test' environment
    """

    # Flask app
    FLASK_ENV: Environment = Environment.TEST


class ProdConfig(_SharedConfig):
    """
    Overrides / default configuration for our deployed 'prod' environment
    """

    # Internal Domains
    INTERNAL_DOMAINS: tuple[str, ...] = ("@communities.gov.uk",)

    # Flask app
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
        case Environment.PULLPREVIEW:
            return PullPreviewConfig()  # type: ignore[call-arg]
        case Environment.TEST:
            return TestConfig()  # type: ignore[call-arg]
        case Environment.PROD:
            return ProdConfig()  # type: ignore[call-arg]

    raise ValueError(f"Unknown environment: {environment}")
