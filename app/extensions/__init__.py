from flask_debugtoolbar import DebugToolbarExtension
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from flask_vite import Vite

from app.extensions.db_request_session import DBRequestSession

db = SQLAlchemy()
db_request_session = DBRequestSession(db=db)
migrate = Migrate()
toolbar = DebugToolbarExtension()
vite = Vite()
