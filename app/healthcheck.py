import ipaddress

from flask import Blueprint, current_app, request
from flask.typing import ResponseReturnValue
from sqlalchemy import text
from werkzeug.http import parse_list_header

healthcheck_blueprint = Blueprint(name="healthcheck", import_name=__name__)


@healthcheck_blueprint.route("/healthcheck")
def healthcheck() -> ResponseReturnValue:
    return "OK", 200, {"content-type": "text/plain"}


def _public_address_or_non_public(remote_addr: str | None) -> str:
    try:
        if remote_addr is not None and ipaddress.ip_address(remote_addr).is_global:
            return remote_addr
    except ValueError:
        pass
    return "non-public"


@healthcheck_blueprint.route("/healthcheck/client")
def client_healthcheck() -> ResponseReturnValue:
    """Report how the app sees the caller, after ProxyFix has applied the X-Forwarded-* headers.

    This lets the post-deploy smoke tests (tests/smoke) prove, through the real proxy chain, that ProxyFix trusts
    exactly the right number of hops and that a client cannot spoof its address, scheme or host.

    It deliberately exposes only the caller's own view of itself (its address as we resolved it, if public, and the
    scheme it used) plus two yes/no answers: whether the request arrived on the canonical host, and whether it carried
    exactly as many X-Forwarded-For entries as PROXY_FIX_FOR expects. Nothing about hostnames or proxy topology leaves
    the server. The resolved address is reported only when it is globally routable: anything else (private, loopback,
    link-local, reserved or unparseable) is reported as "non-public", so a misconfigured ProxyFix cannot publish the
    load balancer's or any other internal address.

    When either answer is no, the detail (the entry count, the configured PROXY_FIX_FOR, the request host and the
    configured SERVER_NAME) is logged at WARNING so it can be investigated in CloudWatch.
    """
    forwarded_for_entries = len(parse_list_header(request.headers.get("X-Forwarded-For", "")))
    expected_forwarded_for_entries = current_app.config["PROXY_FIX_FOR"]
    server_name = current_app.config["SERVER_NAME"]

    host_is_canonical = request.host == server_name
    forwarded_for_matches_config = forwarded_for_entries == expected_forwarded_for_entries

    if not (host_is_canonical and forwarded_for_matches_config):
        current_app.logger.warning(
            "Client healthcheck mismatch: %(forwarded_for_entries)s X-Forwarded-For entries (PROXY_FIX_FOR is "
            "%(expected_forwarded_for_entries)s), host %(host)s (SERVER_NAME is %(server_name)s)",
            {
                "forwarded_for_entries": forwarded_for_entries,
                "expected_forwarded_for_entries": expected_forwarded_for_entries,
                "host": request.host,
                "server_name": server_name,
            },
        )

    return (
        {
            "remote_addr": _public_address_or_non_public(request.remote_addr),
            "scheme": request.scheme,
            "host_is_canonical": host_is_canonical,
            "forwarded_for_matches_config": forwarded_for_matches_config,
        },
        200,
        {"Cache-Control": "no-store"},
    )


@healthcheck_blueprint.route("/healthcheck/db")
def db_healthcheck_current_revision() -> ResponseReturnValue:
    try:
        db = current_app.extensions["sqlalchemy"]
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return result, 200, {"content-type": "text/plain"}
    except Exception:
        current_app.logger.exception("Database healthcheck error")
        return "ERROR", 500, {"content-type": "text/plain"}
