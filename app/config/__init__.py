# TODO: all of this
import os


class Config:
    SQLALCHEMY_ENGINES = {
        "default": os.environ['DATABASE_URL']
    }
    SECRET_KEY = 'unsafe'
    DEBUG_TB_ENABLED = True
