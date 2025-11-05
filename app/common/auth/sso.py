from typing import Any

import msal
from flask import current_app, url_for

# Known error codes that can be returned when we build an MSAL app that we want to handle
MSAL_ERROR_AUTHORIZATION_CODE_WAS_ALREADY_REDEEMED = 54005


def build_msal_app(
    cache: msal.TokenCache | None = None, authority: str | None = None
) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        current_app.config["AZURE_AD_CLIENT_ID"],
        authority=authority or current_app.config["AZURE_AD_AUTHORITY"],
        client_credential=current_app.config["AZURE_AD_CLIENT_SECRET"],
        token_cache=cache,
        instance_discovery=False,
    )


def build_auth_code_flow(authority: str | None = None, scopes: list[str] | None = None) -> dict[str, Any]:
    auth_code_flow: dict[str, Any] = build_msal_app(authority=authority).initiate_auth_code_flow(
        scopes or [], redirect_uri=url_for("auth.sso_get_token", _external=True)
    )
    return auth_code_flow
