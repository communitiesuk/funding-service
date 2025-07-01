from typing import Any

from flask import Blueprint

developers_blueprint = Blueprint(
    name="developers", import_name=__name__, url_prefix="/developers", cli_group="developers"
)


@developers_blueprint.context_processor
def inject_variables() -> dict[str, Any]:
    return dict(show_watermark=True)


from app.developers import access_routes, commands, deliver_routes  # noqa: E402, F401

developers_blueprint.register_blueprint(deliver_routes.developers_deliver_blueprint)
developers_blueprint.register_blueprint(access_routes.developers_access_blueprint)
