import json
from typing import Callable, Dict, Optional

from flask import url_for
from flask.sansio.app import App
from pydantic import BaseModel, RootModel

from app.config import Environment


class Asset(BaseModel):
    file: str
    name: Optional[str] = None
    src: str
    isEntry: bool


class Manifest(RootModel[Optional[Dict[str, Asset]]]):
    root: Optional[Dict[str, Asset]]

    def __getitem__(self, item: str) -> Asset | None:
        if self.root:
            try:
                return self.root[item]
            except KeyError:
                pass
        return None


class FlaskAssetsViteExtension:
    def init_app(self, app: App) -> None:
        self._app = app
        self._live_enabled = self._app.config["ASSETS_VITE_LIVE_ENABLED"]

        try:
            with open("app/assets/dist/manifest.json", "r") as f:
                data = json.load(f)
                self._manifest = Manifest(**data)
        except FileNotFoundError as e:
            if not self._live_enabled or self._app.config["FLASK_ENV"] == Environment.PROD:
                raise Exception("Asset manifest not found, make sure assets are generated") from e

        app.extensions["flask_assets_vite"] = self
        app.context_processor(self.assets_processor)

    def assets_processor(self) -> dict[str, Callable[[str], str]]:
        def vite_asset(relative_file_path: str) -> str:
            """
            Point assets at a vite development server while running locally
            to enable hot module replacement and automatic udpates to both SCSS
            and JavaScript.
            """

            if self._live_enabled:
                return f"{self._app.config['ASSETS_VITE_BASE_URL']}/static/{relative_file_path}"

            generated_asset = self._manifest[relative_file_path]
            if generated_asset:
                # assets that have been transpiled by vite should reference their hashed names
                return url_for("static", filename=generated_asset.file)

            # assets that have not been transpiled by vite but may have been copied
            return url_for("static", filename=relative_file_path)

        return dict(vite_asset=vite_asset)
