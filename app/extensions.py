from flask_debugtoolbar import DebugToolbarExtension
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy

from app.common.data.base import BaseModel

db = SQLAlchemy()
migrate = Migrate(metadatas=BaseModel.metadata)
toolbar = DebugToolbarExtension()
