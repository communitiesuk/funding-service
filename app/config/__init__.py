# TODO: all of this
import os


class Config:
    SQLALCHEMY_ENGINES = {"default": os.environ["DATABASE_URL"]}
    SERVER_NAME = "funding.communities.gov.localhost:8080"
    SECRET_KEY = "unsafe"  # pragma: allowlist secret
    DEBUG_TB_ENABLED = True
