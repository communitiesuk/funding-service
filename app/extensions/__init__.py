from flask_debugtoolbar import DebugToolbarExtension
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from flask_vite import Vite

db = SQLAlchemy()
migrate = Migrate()
toolbar = DebugToolbarExtension()
vite = Vite()
