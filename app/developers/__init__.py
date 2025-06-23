from flask import Blueprint

developers_deliver_blueprint = Blueprint(
    name="developers_dgf", import_name=__name__, url_prefix="/developers/deliver", cli_group="developers"
)

from app.developers import commands, routes  # noqa: E402, F401
