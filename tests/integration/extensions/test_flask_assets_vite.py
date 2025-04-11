from unittest.mock import patch

import pytest
from flask import Flask

from app.extensions.flask_assets_vite import Environment, FlaskAssetsViteExtension


@pytest.fixture(scope="module")
def db_session():
    pass


@pytest.fixture(scope="function")
def app():
    app = Flask(__name__)
    app.config["FLASK_ENV"] = Environment.LOCAL
    app.config["ASSETS_VITE_BASE_URL"] = "http://funding.localhost:8080"
    yield app


def get_template_processor(app, name):
    # this seems gross but it doesn't seem like context processors are attached to app.jinja_env.globals
    # so fetching it out of the this list to assert its also been registered on the app corretly
    return next(p() for p in app.template_context_processors.get(None, []) if name in p())[name]


def test_assets_live_enabled(app):
    app.config["ASSETS_VITE_LIVE_ENABLED"] = True

    FlaskAssetsViteExtension().init_app(app)

    with app.app_context():
        vite_asset = get_template_processor(app, "vite_asset")
        assert vite_asset("asset.js") == "http://funding.localhost:8080/static/asset.js"


def test_assets_static_manifest(app):
    app.config["ASSETS_VITE_LIVE_ENABLED"] = False

    manifest_data = {"asset.js": {"file": "asset.unique-hash.js", "src": "asset.js", "isEntry": True}}

    with patch("builtins.open"), patch("json.load", return_value=manifest_data):
        FlaskAssetsViteExtension().init_app(app)

    with app.app_context():
        vite_asset = get_template_processor(app, "vite_asset")
        assert vite_asset("asset.js") == "/static/asset.unique-hash.js"
        assert vite_asset("not_transpiled.js") == "/static/not_transpiled.js"


def test_assets_no_manifest_production(app):
    app.config["ASSETS_VITE_LIVE_ENABLED"] = False
    app.config["FLASK_ENV"] = Environment.PROD

    with pytest.raises(Exception, match="Asset manifest not found, make sure assets are generated"):
        with patch("builtins.open", side_effect=FileNotFoundError):
            FlaskAssetsViteExtension().init_app(app)


def test_assets_no_manifest_non_production(app):
    app.config["ASSETS_VITE_LIVE_ENABLED"] = True

    extension = FlaskAssetsViteExtension()

    with patch("builtins.open", side_effect=FileNotFoundError):
        extension.init_app(app)  # no error is raised as we're using the dev vite server
