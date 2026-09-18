import uuid

from flask import abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_deliver_grant_role, has_feature_flag_enabled
from app.common.data.interfaces.collections import delete_collection, get_collection
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import CollectionType, RoleEnum
from app.common.forms import GenericConfirmDeletionForm
from app.common.helpers.feature_flags import FeatureFlags
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.extensions import auto_commit_after_request


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/pre-award", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.MEMBER)
@has_feature_flag_enabled(FeatureFlags.PRE_AWARD)
@auto_commit_after_request
def list_pre_award_forms(grant_id: uuid.UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)

    delete_wtform, delete_pre_award_form = None, None
    if delete_pre_award_form_id := request.args.get("delete"):
        if not AuthorisationHelper.can_edit_collection(
            user=get_current_user(), collection_id=uuid.UUID(delete_pre_award_form_id)
        ):
            return redirect(url_for("deliver_grant_funding.list_pre_award_forms", grant_id=grant_id))

        delete_pre_award_form = get_collection(
            uuid.UUID(delete_pre_award_form_id), grant_id=grant_id, type_=CollectionType.APPLICATION
        )
        if delete_pre_award_form.live_submissions:
            abort(403)

        if delete_pre_award_form and not delete_pre_award_form.live_submissions:
            delete_wtform = GenericConfirmDeletionForm()

            if delete_wtform and delete_wtform.validate_on_submit():
                delete_collection(delete_pre_award_form)

                return redirect(url_for("deliver_grant_funding.list_pre_award_forms", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/pre_award/list_pre_award_forms.html",
        grant=grant,
        delete_form=delete_wtform,
        delete_pre_award_form=delete_pre_award_form,
    )
