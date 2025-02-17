# TODO: all of this
import os
from typing import Literal


class Config:
    # Flask app
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    SERVER_NAME = "funding.communities.gov.localhost:8080"
    SECRET_KEY = "unsafe"  # pragma: allowlist secret

    # Databases
    SQLALCHEMY_ENGINES = {
        "default": os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        )
    }

    # Logging
    LOG_LEVEL = "INFO"
    LOG_FORMATTER: Literal["plaintext", "json"] = "json"

    # Flask-DebugToolbar
    DEBUG_TB_ENABLED = True
