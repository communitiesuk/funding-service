from flask import Blueprint, render_template
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.grants import add_grant
from app.extensions import db
from app.platform.forms import GrantForm

# TODO do we call this platform
platform_blueprint = Blueprint(name="platform", import_name=__name__)


# TODO think about a naming convention for route handlers
@platform_blueprint.route("/grant", methods=["GET", "POST"])
def create_grant() -> str:
    form = GrantForm()
    if form.validate_on_submit():
        with db.get_session() as session, session.begin():
            try:
                add_grant(name=form.name.data)  # type: ignore
            except IntegrityError:
                # Typing error on next line is because errors is defined as a tuple but at runtime is a list
                form.name.errors.append("Grant name already in use")  # type:ignore[attr-defined]
    return render_template("platform/grant.html", form=form)
