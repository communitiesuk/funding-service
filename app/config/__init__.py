# TODO: all of this
import os


class Config:
    SQLALCHEMY_ENGINES = {
        "default": os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
        )
    }
    SECRET_KEY = "unsafe"
    DEBUG_TB_ENABLED = True
