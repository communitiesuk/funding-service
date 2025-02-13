# TODO: all of this
class Config:
    SQLALCHEMY_ENGINES = {
        "default": "sqlite:///default.sqlite"
    }
    SECRET_KEY = 'unsafe'
    DEBUG_TB_ENABLED = True
