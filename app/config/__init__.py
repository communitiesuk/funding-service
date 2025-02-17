# TODO: all of this
import os


class Config:
    SQLALCHEMY_ENGINES = {
        "default": os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        )
    }
    SERVER_NAME = "funding.communities.gov.localhost:8080"
    SECRET_KEY = "unsafe"
    DEBUG_TB_ENABLED = True
