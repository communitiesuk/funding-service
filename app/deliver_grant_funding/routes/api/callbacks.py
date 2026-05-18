import datetime
import enum
import secrets
import uuid
from typing import TYPE_CHECKING, Literal

import sentry_sdk
from flask import current_app, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import BaseModel, ValidationError

from app.common.audit import create_system_event_for_delete
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.audit import track_audit_event
from app.common.data.interfaces.grant_recipients import get_grant_recipients_for_organisation
from app.common.data.interfaces.user import (
    get_or_create_system_user,
    get_user_by_email,
    get_users_covering_grant_role,
    remove_all_roles_from_user,
)
from app.common.data.types import GrantRecipientModeEnum, OrganisationModeEnum, RoleEnum
from app.deliver_grant_funding.routes.api import deliver_grant_funding_api_blueprint
from app.extensions import auto_commit_after_request

if TYPE_CHECKING:
    from app.common.data.models import Grant, Organisation
    from app.common.data.models_user import User


class GovukNotifyStatus(enum.StrEnum):
    DELIVERED = "delivered"

    TEMPORARY_FAILURE = "temporary-failure"
    PERMANENT_FAILURE = "permanent-failure"
    TECHNICAL_FAILURE = "technical-failure"


class GovukNotifyCallbackModel(BaseModel):
    id: uuid.UUID
    reference: str | None

    notification_type: Literal["email", "sms"]
    template_id: uuid.UUID
    template_version: int

    to: str
    status: GovukNotifyStatus

    created_at: datetime.datetime
    sent_at: datetime.datetime | None
    completed_at: datetime.datetime | None


def handle_permanent_email_failure(notification_id: uuid.UUID, recipient_email: str) -> None:
    user = get_user_by_email(recipient_email)
    if user is None:
        current_app.logger.error(
            "GOV.UK Notify permanent failure for unknown user: %(recipient_email)s",
            dict(recipient_email=recipient_email),
        )
        return

    if AuthorisationHelper.is_deliver_grant_funding_user(user):
        # Specifically ignore Deliver grant funding users for now - TBD what we should do in the future.
        current_app.logger.info(
            "GOV.UK Notify permanent failure for Deliver grant funding user: %(user_id)s. No action taken.",
            dict(user_id=user.id),
        )
        return

    access_grant_funding_roles = _get_access_grant_funding_roles_for_user(user)

    system_user = get_or_create_system_user()
    audit_events = [
        create_system_event_for_delete(
            ur,
            system_user,
            context=dict(
                notification_id=notification_id, reason="GOV.UK Notify callback indicated permanent delivery failure"
            ),
        )
        for ur in user.roles
    ]

    remove_all_roles_from_user(user)

    for event in audit_events:
        track_audit_event(event, system_user)

    _log_error_for_access_grant_funding_roles_with_no_alternate_users(
        access_grant_funding_roles, exclude_user_id=None, reason="permanent failure"
    )


def handle_temporary_email_failure(recipient_email: str) -> None:
    user = get_user_by_email(recipient_email)
    if user is None:
        current_app.logger.error(
            "GOV.UK Notify temporary failure for unknown user: %(recipient_email)s",
            dict(recipient_email=recipient_email),
        )
        return

    if AuthorisationHelper.is_deliver_grant_funding_user(user):
        # Specifically ignore Deliver grant funding users for now - TBD what we should do in the future.
        current_app.logger.info(
            "GOV.UK Notify temporary failure for Deliver grant funding user: %(user_id)s. No action taken.",
            dict(user_id=user.id),
        )
        return

    access_grant_funding_roles = _get_access_grant_funding_roles_for_user(user)
    _log_error_for_access_grant_funding_roles_with_no_alternate_users(
        access_grant_funding_roles, exclude_user_id=user.id, reason="temporary failure"
    )


def _get_access_grant_funding_roles_for_user(
    user: "User",
) -> list[tuple["Organisation", "Grant", RoleEnum]]:
    triples: list[tuple[Organisation, Grant, RoleEnum]] = []
    for ur in user.roles:
        if (
            ur.organisation is None
            or ur.organisation.can_manage_grants
            or ur.organisation.mode != OrganisationModeEnum.LIVE
        ):
            continue

        roles_present = [r for r in RoleEnum.get_access_grant_funding_roles() if r in ur.permissions]
        if not roles_present:
            continue

        if ur.grant_id is not None:
            grants: list[Grant] = [ur.grant]
        else:
            grants = [
                gr.grant
                for gr in get_grant_recipients_for_organisation(ur.organisation.id, mode=GrantRecipientModeEnum.LIVE)
            ]

        for grant in grants:
            for role in roles_present:
                triples.append((ur.organisation, grant, role))
    return triples


def _log_error_for_access_grant_funding_roles_with_no_alternate_users(
    access_grant_funding_roles: list[tuple["Organisation", "Grant", RoleEnum]],
    *,
    exclude_user_id: uuid.UUID | None,
    reason: str,
) -> None:
    seen: set[tuple[uuid.UUID, uuid.UUID, RoleEnum]] = set()
    for organisation, grant, role in access_grant_funding_roles:
        key = (organisation.id, grant.id, role)
        if key in seen:
            continue
        seen.add(key)
        remaining = get_users_covering_grant_role(role, grant, organisation, exclude_user_id=exclude_user_id)
        if not remaining:
            current_app.logger.error(
                "Grant '%(grant_name)s' (%(grant_id)s) at organisation '%(organisation_name)s' "
                "(%(organisation_id)s) has no other users with %(role_name)s after %(reason)s; "
                "manual intervention required.",
                dict(
                    grant_name=grant.name,
                    grant_id=grant.id,
                    organisation_name=organisation.name,
                    organisation_id=organisation.id,
                    role_name=role.name,
                    reason=reason,
                ),
            )


@deliver_grant_funding_api_blueprint.post("/govuk-notify-callback")
@auto_commit_after_request
def govuk_notify_callback() -> ResponseReturnValue:
    if not current_app.config["GOVUK_NOTIFY_CALLBACK_TOKEN"]:
        return jsonify(), 500

    if (
        not request.authorization
        or not request.authorization.token
        or not secrets.compare_digest(
            request.authorization.token.encode(), current_app.config["GOVUK_NOTIFY_CALLBACK_TOKEN"].encode()
        )
    ):
        return jsonify(), 403

    if request.mimetype != "application/json":
        current_app.logger.error(
            "GOV.UK Notify callback received with invalid content type: %(mimetype)s", dict(mimetype=request.mimetype)
        )
        return jsonify(), 400

    try:
        callback_data = GovukNotifyCallbackModel.model_validate_json(request.data)
    except ValidationError as e:
        sentry_sdk.capture_exception(e)
        return jsonify(), 400

    with sentry_sdk.new_scope() as scope:
        scope.set_context("notify_callback", callback_data.model_dump(mode="json"))

        if callback_data.notification_type != "email":
            current_app.logger.warning(
                "GOV.UK Notify callback received for unhandled notification type: %(notification_type)s",
                dict(notification_type=callback_data.notification_type),
            )
            return jsonify(), 202

        if callback_data.to.endswith(current_app.config["GOVUK_NOTIFY_IGNORE_CALLBACK_DOMAINS"]):
            return jsonify(), 202

        if callback_data.status == GovukNotifyStatus.PERMANENT_FAILURE:
            handle_permanent_email_failure(callback_data.id, callback_data.to)
            return jsonify(), 202

        if callback_data.status == GovukNotifyStatus.TEMPORARY_FAILURE:
            handle_temporary_email_failure(callback_data.to)
            return jsonify(), 202

        if callback_data.status != GovukNotifyStatus.DELIVERED:
            current_app.logger.error(
                "GOV.UK Notify callback indicates %(status)s for email notification",
                dict(status=callback_data.status),
            )
            return jsonify(), 202

    return jsonify(), 204
