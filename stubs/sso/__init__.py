"""
This stub server is set up to (minimally) implement an oauth interface flow, as used by MIcrosoft AD, for local
development and locally-run end to end tests.

It runs on a separate docker container and implements the basic routes needed as part of the SSO flow, returning dummy
payloads with only certain key values included (anything that can be anonymised, randomised or made into an empty string
has been). The Funding Service app knows to hit the stub server in this flow because the AZURE_AD_AUTHORITY config
variable is set to point to sso.communities.gov.localhost.

This flow also implements a small email input form as part of the flow so that the redirects can be tested and we can
also pass that email through to the `get_or_create_user` method and check behaviour with specific emails and domains.

"""

import base64
import json
import time
import uuid
from urllib.parse import urlencode

from flask import Flask, redirect, render_template, request
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader

from stubs.sso.forms import SSOSignInForm

app = Flask(__name__)
app.config["SECRET_KEY"] = "dummy-value"  # pragma: allowlist secret
app.config["INTERNAL_DOMAINS"] = ("@communities.gov.uk", "@test.communities.gov.uk")

app.jinja_loader = ChoiceLoader(
    [
        PackageLoader("stubs.sso"),
        PrefixLoader({"govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja")}),
        PrefixLoader({"govuk_frontend_wtf": PackageLoader("govuk_frontend_wtf")}),
    ]
)

WTFormsHelpers(app)

dummy_nonce = ""
email_address = ""

dummy_client_info = {"uid": str(uuid.uuid4()), "utid": str(uuid.uuid4())}
json_dummy_client_info = json.dumps(dummy_client_info)
base_64_str_client_info = base64.b64encode(json_dummy_client_info.encode()).decode()


@app.route("/<tenant>/oauth2/v2.0/authorize", methods=["GET", "POST"])
def oauth_redirect(tenant):
    global dummy_nonce, base_64_str_client_info, email_address

    form = SSOSignInForm()
    if form.validate_on_submit():
        dummy_nonce = request.args["nonce"]
        email_address = form.email_address.data
        data = urlencode(
            {
                "code": "dummy value",
                "client_info": base_64_str_client_info,
                "state": request.args["state"],
                "session_state": uuid.uuid4(),
            }
        )
        return redirect(request.args["redirect_uri"] + "?" + data)
    return render_template("sso/sso_login.html", form=form)


@app.route("/<tenant>/v2.0/.well-known/openid-configuration")
def openid_configuration(tenant):
    # There are a number of URIs in this dict which we haven't defined in the stub server (eg. jwks_uri,
    # userinfo_endpoint etc.) which don't get used as part of this journey. If we remove these from the payload
    # it seems to break the server so they need to be there even if they're not used.
    return {
        "token_endpoint": f"https://{request.host}/{tenant}/oauth2/v2.0/token",
        "token_endpoint_auth_methods_supported": ["client_secret_post", "private_key_jwt", "client_secret_basic"],
        "jwks_uri": f"https://{request.host}/{tenant}/discovery/v2.0/keys",  # Not used
        "response_modes_supported": ["query", "fragment", "form_post"],
        "subject_types_supported": ["pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "response_types_supported": ["code", "id_token", "code id_token", "id_token token"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "issuer": f"https://{request.host}/{tenant}/v2.0",  # Not used
        "request_uri_parameter_supported": False,
        "userinfo_endpoint": f"https://{request.host}/oidc/userinfo",  # Not used
        "authorization_endpoint": f"https://{request.host}/{tenant}/oauth2/v2.0/authorize",
        "device_authorization_endpoint": f"https://{request.host}/{tenant}/oauth2/v2.0/devicecode",  # Not used
        "http_logout_supported": True,
        "frontchannel_logout_supported": True,
        "end_session_endpoint": f"https://{request.host}/{tenant}/oauth2/v2.0/logout",  # Not used
        "claims_supported": [
            "sub",
            "iss",
            "cloud_instance_name",
            "cloud_instance_host_name",
            "cloud_graph_host_name",
            "msgraph_host",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "acr",
            "nonce",
            "preferred_username",
            "name",
            "tid",
            "ver",
            "at_hash",
            "c_hash",
            "email",
        ],
        "kerberos_endpoint": f"https://{request.host}/{tenant}/kerberos",  # Not used
        "tenant_region_scope": "EU",
        "cloud_instance_name": request.host,
        # These are dummy values
        "cloud_graph_host_name": "graph.mhclg.localhost",
        "msgraph_host": "graph.mhclg.localhost",
        "rbac_url": "https://pas.mhclg.localhost",
    }


@app.route("/<tenant>/oauth2/v2.0/token", methods=["GET", "POST"])
def token_endpoint(tenant):
    global dummy_nonce, base_64_str_client_info, email_address

    # We've replaced a lot of the values in this dictionary with empty strings as they won't be referenced anywhere else
    # The only ones that are needed are the global variables, roles and timestamps.
    # For more info on these look at the docs https://learn.microsoft.com/en-us/entra/identity-deliver_grant_funding/id-token-claims-reference
    return {
        "token_type": "Bearer",
        "scope": "User.Read User.ReadBasic.All profile openid email",
        "expires_in": 3980,
        "ext_expires_in": 3980,
        "access_token": "",
        "refresh_token": "",
        "client_info": base_64_str_client_info,
        "id_token_claims": {
            "aud": "",
            "iss": "",
            "iat": int(time.time()),
            "nbf": int(time.time()),
            "exp": int(time.time() + 60 * 60),
            "idp": "",
            "name": "Dev Developer",
            "nonce": dummy_nonce,
            "oid": "",
            "preferred_username": email_address,
            "rh": "",
            "roles": ["FSD_ADMIN"],
            "sid": "",
            "sub": "",
            "tid": "",
            "uti": "",
            "ver": "2.0",
        },
        "token_source": "identity_provider",
    }
