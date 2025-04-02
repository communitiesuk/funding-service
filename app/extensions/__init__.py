from flask_debugtoolbar import DebugToolbarExtension
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from flask_vite import Vite

from app.extensions.auto_commit_after_request import AutoCommitAfterRequestExtension

db = SQLAlchemy()
auto_commit_after_request = AutoCommitAfterRequestExtension(db=db)
migrate = Migrate()
toolbar = DebugToolbarExtension()
vite = Vite()
