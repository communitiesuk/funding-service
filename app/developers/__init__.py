from flask import Blueprint

developers_blueprint = Blueprint(
    name="developers", import_name=__name__, url_prefix="/developers", cli_group="developers"
)


from app.developers import commands as commands  # noqa: E402, F401
