import uuid
from typing import TYPE_CHECKING
from uuid import UUID

from flask import abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import has_deliver_grant_role
from app.common.data.interfaces.collections import (
    delete_collection,
    get_collection,
)
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import (
    CollectionType,
    RoleEnum,
)
from app.common.forms import GenericConfirmDeletionForm
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.deliver_grant_funding.session_models import (
    AddConditionDependsOnSessionModel,
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
)
from app.extensions import auto_commit_after_request

if TYPE_CHECKING:
    pass

SessionModelType = (
    AddConditionDependsOnSessionModel
    | AddContextToComponentSessionModel
    | AddContextToComponentGuidanceSessionModel
    | AddContextToExpressionsModel
)


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/reports", methods=["GET", "POST"])
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_reports(grant_id: UUID) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)

    delete_wtform, delete_report = None, None
    if delete_report_id := request.args.get("delete"):
        if not AuthorisationHelper.can_edit_collection(
            user=get_current_user(), collection_id=uuid.UUID(delete_report_id)
        ):
            return redirect(url_for("deliver_grant_funding.list_reports", grant_id=grant_id))

        delete_report = get_collection(
            uuid.UUID(delete_report_id), grant_id=grant_id, type_=CollectionType.MONITORING_REPORT
        )
        if delete_report.live_submissions:
            abort(403)

        if delete_report and not delete_report.live_submissions:
            delete_wtform = GenericConfirmDeletionForm()

            if delete_wtform and delete_wtform.validate_on_submit():
                delete_collection(delete_report)

                return redirect(url_for("deliver_grant_funding.list_reports", grant_id=grant_id))

    return render_template(
        "deliver_grant_funding/reports/list_reports.html",
        grant=grant,
        delete_form=delete_wtform,
        delete_report=delete_report,
    )
