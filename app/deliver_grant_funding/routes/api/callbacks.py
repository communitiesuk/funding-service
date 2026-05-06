import datetime
import enum
import secrets
import uuid
from typing import Literal

import sentry_sdk
from flask import current_app, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import BaseModel, ValidationError

from app.deliver_grant_funding.routes.api import deliver_grant_funding_api_blueprint


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


@deliver_grant_funding_api_blueprint.post("/govuk-notify-callback")
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
        sentry_sdk.capture_message(
            f"GOV.UK Notify callback received with invalid content type: {request.mimetype}", level="error"
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
            sentry_sdk.capture_message(
                f"GOV.UK Notify callback received for unhandled notification type: {callback_data.notification_type}",
                level="warning",
            )
            return jsonify(), 202

        if callback_data.to.endswith(current_app.config["GOVUK_NOTIFY_IGNORE_CALLBACK_DOMAINS"]):
            return jsonify(), 202

        if callback_data.status != GovukNotifyStatus.DELIVERED:
            sentry_sdk.capture_message(
                f"GOV.UK Notify callback indicates {callback_data.status} for email notification",
                level="error",
            )
            return jsonify(), 202

    return jsonify(), 204
