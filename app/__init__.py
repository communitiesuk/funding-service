import json
from typing import Dict, Optional

from flask import Flask, url_for
from flask_babel import Babel
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader
from pydantic import BaseModel as PydnaticBaseModel
from pydantic import RootModel

from app import logging
from app.config import get_settings
from app.extensions import auto_commit_after_request, db, migrate, notification_service, toolbar
from app.sentry import init_sentry

init_sentry()


def create_app() -> Flask:
    from app.common.data.base import BaseModel

    # there's something slightly unusual about how the govuk frontend jinja assets will
    # refer to whats built in the flask app
    # (i.e the manifest.json, the MHCLG crest)
    # and things built into the CSS will refer to the same host they came from
    # (the dev server, locally) but can cross that bridge
    # (i.e the font files, the GOVUK logo SVG)

    # implicastion: if you _just_ run the dev server it won't have moved
    # the files and they won't be served (i.e you'll need an actual build first)
    # that's probably fine but an alternative would be to point the MHCLG crest + manifest
    # to the dev server
    # they're both set in HTML templates so setting `assetPath` and then using
    # that in both places should do it
    app = Flask(__name__, static_folder="assets/dist/", static_url_path="/static")
    app.config.from_object(get_settings())

    # when developing we want the toolbar assets to not cause the page to flicker
    # should make an intentional decision for when to be setting this
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

    # Initialise extensions
    logging.init_app(app)
    db.init_app(app)
    auto_commit_after_request.init_app(app)
    migrate.init_app(
        app,
        db,  # type: ignore[arg-type]  # not natively compatible with Flask-SQLAlchemy-Lite; but is fine for us.
        directory="app/common/data/migrations",
        compare_type=True,
        render_as_batch=True,
        metadatas=BaseModel.metadata,
    )
    toolbar.init_app(app)
    notification_service.init_app(app)

    # Configure templates
    app.jinja_loader = ChoiceLoader(
        [
            PackageLoader("app.common"),
            PackageLoader("app.platform"),
            PrefixLoader({"govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja")}),
            PrefixLoader({"govuk_frontend_wtf": PackageLoader("govuk_frontend_wtf")}),
        ]
    )
    WTFormsHelpers(app)

    Babel(app)
    app.jinja_env.add_extension("jinja2.ext.i18n")

    # Attach routes
    from app.common.auth import auth_blueprint
    from app.healthcheck import healthcheck_blueprint
    from app.platform import platform_blueprint

    app.register_blueprint(healthcheck_blueprint)
    app.register_blueprint(platform_blueprint)
    app.register_blueprint(auth_blueprint)

    class Asset(PydnaticBaseModel):
        file: str
        name: Optional[str] = None
        src: str
        isEntry: bool

    # Manifest = RootModel(Optional[Dict[str, Asset]])
    # Manifest = RootModel(root=Asset)

    class Manifest(RootModel):
        root: Optional[Dict[str, Asset]]

        def __getitem__(self, item):
            return self.root[item]

    @app.context_processor
    def assets_processor():
        def vite_asset(relative_file_path: str):
            """
            Point assets at a vite development server while running locally
            to enable hot module replacement and automatic udpates to both SCSS
            and JavaScript.
            """
            try:
                with open("app/assets/dist/manifest.json", "r") as f:
                    data = json.load(f)
                    manifest = Manifest(**data)
            except:
                pass

            # I need to lookup the manifest from here - that's where moving
            # this out to an extension will feel much cleaner I think

            # if app.config["FLASK_ENV"] == Environment.LOCAL and app.debug:
            # return f"{app.config['ASSETS_VITE_BASE_URL']}{relative_file_path}"
            # else:

            # note: this doesn't actually work if theres no manifest
            # we'll look it up first in the manieft map - otherwise just point at it
            if manifest:
                try:
                    # this will be a key error if this doesn't exist - there's probably a nicer way
                    known_asset = manifest[relative_file_path]
                    return url_for("static", filename=known_asset.file)
                except:
                    pass

            # return f"/{relative_file_path}"
            return url_for("static", filename=relative_file_path)

        return dict(vite_asset=vite_asset)

    return app
