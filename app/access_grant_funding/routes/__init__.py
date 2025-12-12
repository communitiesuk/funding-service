from flask import Blueprint

access_grant_funding_blueprint = Blueprint(name="access_grant_funding", import_name=__name__, url_prefix="/access")


@access_grant_funding_blueprint.context_processor
def inject_testing_context() -> dict[str, bool]:
    """Make testing flag available to all access grant funding templates."""
    from app.common.auth.authorisation_helper import AuthorisationHelper
    from app.common.data.interfaces.user import get_current_user

    user = get_current_user()
    return {"is_deliver_user_testing": AuthorisationHelper.is_deliver_user_testing_access(user)}


from app.access_grant_funding.routes import (  # noqa: E402, F401
    misc,
    reports,
    runner,
)
