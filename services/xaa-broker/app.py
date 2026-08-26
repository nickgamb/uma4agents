"""xaa-broker — Northwind's cross-app access endpoint.

This is the half of the picture UMA has never had an opinion about: *whose
agent is this, and has the enterprise already agreed that it may reach that
application at all?*

Cross App Access answers it the way an enterprise already answers every other
access question — at the identity provider both applications trust for SSO.
An administrator configures a connection between a requesting application and
a resource application, and the identity provider mints an assertion saying
so. No end user consents to anything, because in this half there is nothing
for an end user to consent to: the employer decided, and the employee's
agreement is to their employment, not to each API call.

The assertion is an **ID-JAG** — an Identity Assertion JWT Authorization
Grant, `draft-ietf-oauth-identity-assertion-authz-grant`. The client exchanges
a subject token (here, an OpenID Connect ID token from Northwind's realm) for
one, audienced at a *specific* authorization server and naming a *specific*
resource. It is short-lived, single-audience, and it carries no entitlement of
its own.

That last point is the whole reason this service and a UMA authorization
server are not competitors:

    this service says   ── which employee, which agent, which application,
                           and that Northwind approved that edge

    her authority says  ── and therefore what it may do to that resource,
                           on whose terms, for how long, at what depth of
                           delegation

Neither can answer the other's question. Northwind cannot know what Alice's
terms say, and Alice's authority cannot know whether Northwind's administrator
approved this agent's application at all. So the ID-JAG arrives at her
authority as a *claim* against an open permission ticket, which is precisely
the slot UMA has always had for "prove something about yourself before I
dictate terms" — and her authority then goes on to ask its own question.

Keycloak is Northwind's identity provider in this lab and holds the employee
directory, but it cannot yet issue an ID-JAG — its support is receiver-side
only, and behind an experimental flag at that. So the exchange endpoint lives
here, beside it, trusting that realm for subject tokens. An Okta tenant with
Cross App Access enabled does both halves in one place; the split here is a
property of the lab, not of the design.

State is in memory. One replica — `make reset` rewinds it.
"""

import base64
import json
import os
import secrets
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ISSUER = os.environ.get("XAA_ISSUER", "https://northwind-xaa.uma.lab")
# The realm holding Northwind's employee directory. A subject token signed by
# anything else is not an employee assertion, whatever it claims.
IDP_ISSUER = os.environ.get("XAA_IDP_ISSUER",
                            "https://keycloak.uma.lab/realms/northwind")
KEY_PATH = os.environ.get("XAA_KEY_PATH", "/keys/xaa-ed25519.pem")
CA_BUNDLE = os.environ.get("UMA4A_CA_BUNDLE") or os.environ.get("UMA4A_CACERT")
# Short by construction. An ID-JAG is spent immediately at one authorization
# server; it is not a credential anybody should be holding.
JAG_TTL = int(os.environ.get("XAA_JAG_TTL_S", "300"))
ADMINS = {a for a in os.environ.get("XAA_ADMINS", "dana").split(",") if a}

GRANT_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_TYPE_ID_JAG = "urn:ietf:params:oauth:token-type:id-jag"
TOKEN_TYPE_ID_TOKEN = "urn:ietf:params:oauth:token-type:id_token"
ID_JAG_TYP = "oauth-id-jag+jwt"


def load_or_create_key() -> Ed25519PrivateKey:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return key


SIGNING_KEY = load_or_create_key()
PUBLIC_JWK = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(SIGNING_KEY.public_key()))
KID = base64.urlsafe_b64encode(
    __import__("hashlib").sha256(
        json.dumps({"crv": PUBLIC_JWK["crv"], "kty": PUBLIC_JWK["kty"],
                    "x": PUBLIC_JWK["x"]}, separators=(",", ":"),
                   sort_keys=True).encode()).digest()).decode().rstrip("=")

app = FastAPI(title="xaa-broker")


def now() -> float:
    return time.time()


def event(name: str, **fields) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "svc": "xaa-broker", "event": name, **fields}),
          flush=True)


# ── Northwind's directory of approved edges ──────────────────────────────────
#
# What an administrator configures in the identity provider, and the only
# thing that makes an exchange succeed. A connection names one requesting
# application, one authorization server it may be sent to, one resource, and
# the widest scope the enterprise will assert for. Nothing here is policy
# about a resource — it is policy about which applications may talk at all.

CONNECTIONS: dict[str, dict] = {}
# Requesting applications registered with Northwind's identity provider, and
# the secret each authenticates the exchange with.
CLIENTS: dict[str, str] = {}
# A dev token so the lab can seed connections without driving a login. The
# same affordance org-authority ships, and the same caveat: it is a lab.
ADMIN_TOKEN = os.environ.get("XAA_ADMIN_TOKEN", "xaa-admin-dev-token")

_JWKS_CACHE: tuple[float, list] = (0.0, [])
JWKS_TTL = 300


def _client() -> httpx.Client:
    return httpx.Client(verify=CA_BUNDLE or True, timeout=10.0)


def idp_keys(fresh: bool = False) -> list:
    """Northwind's realm signing keys, via OpenID discovery."""
    global _JWKS_CACHE
    age, keys = _JWKS_CACHE
    if keys and not fresh and now() - age < JWKS_TTL:
        return keys
    with _client() as c:
        conf = c.get(f"{IDP_ISSUER}/.well-known/openid-configuration").json()
        jwks = c.get(conf["jwks_uri"]).json()
    _JWKS_CACHE = (now(), jwks.get("keys", []))
    return _JWKS_CACHE[1]


def verify_subject_token(token: str, client_id: str) -> dict:
    """An ID token from Northwind's realm, issued to the client presenting it.

    The audience check is the one that matters and the easy one to skip. A
    client that could exchange *any* employee's token it happened to obtain
    would be a confused deputy with an enterprise-wide blast radius, so the
    token has to have been minted for this client."""
    try:
        head = jwt.get_unverified_header(token)
    except Exception as exc:
        raise ValueError(f"subject token is not a JWT: {exc}")

    keys = idp_keys()
    kid = head.get("kid")
    if kid and not any(k.get("kid") == kid for k in keys):
        keys = idp_keys(fresh=True)  # a rotated realm key, not a bad token

    claims = None
    for jwk_dict in keys:
        if kid and jwk_dict.get("kid") != kid:
            continue
        try:
            key = jwt.PyJWK(jwk_dict).key
            claims = jwt.decode(token, key, algorithms=[head.get("alg", "RS256")],
                                issuer=IDP_ISSUER,
                                options={"verify_aud": False})
            break
        except jwt.InvalidTokenError:
            continue
    if claims is None:
        raise ValueError("subject token does not verify against the realm")

    aud = claims.get("aud")
    aud = [aud] if isinstance(aud, str) else list(aud or [])
    if client_id not in aud and claims.get("azp") != client_id:
        raise ValueError("subject token was not issued to this client")
    if not claims.get("sub"):
        raise ValueError("subject token has no subject")
    return claims


def connection_for(client_id: str, audience: str, resource: str) -> dict | None:
    for conn in CONNECTIONS.values():
        if (conn.get("enabled")
                and conn["requesting_client"] == client_id
                and conn["audience"] == audience
                and conn["resource"] == resource):
            return conn
    return None


def authenticate_client(request: Request, form) -> str:
    """Client authentication, `client_secret_basic` or `client_secret_post`."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        from urllib.parse import unquote
        try:
            raw = base64.b64decode(auth.split(" ", 1)[1]).decode()
        except Exception:
            raise ValueError("malformed basic credentials")
        cid, _, sec = raw.partition(":")
        cid, sec = unquote(cid), unquote(sec)
    else:
        cid, sec = form.get("client_id") or "", form.get("client_secret") or ""
    known = CLIENTS.get(cid)
    if not cid or known is None or not secrets.compare_digest(known, sec):
        raise ValueError("unknown client or bad secret")
    return cid


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    """RFC 8693 token exchange, profiled by the ID-JAG draft.

    Every refusal here is Northwind declining to *assert* something. None of
    them is a decision about a resource — that decision is not this service's
    to make, and an ID-JAG minted successfully is still not an access token."""
    form = await request.form()

    if (form.get("grant_type") or "") != GRANT_TOKEN_EXCHANGE:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    # This endpoint mints one kind of token. Asking for anything else is not a
    # request it can partially honour.
    if (form.get("requested_token_type") or "") != TOKEN_TYPE_ID_JAG:
        return JSONResponse(
            {"error": "invalid_request",
             "error_description": f"requested_token_type must be {TOKEN_TYPE_ID_JAG}"},
            status_code=400)

    try:
        client_id = authenticate_client(request, form)
    except ValueError as exc:
        event("exchange.refused", reason="client-auth", detail=str(exc))
        return JSONResponse({"error": "invalid_client"}, status_code=401)

    if (form.get("subject_token_type") or "") != TOKEN_TYPE_ID_TOKEN:
        return JSONResponse(
            {"error": "invalid_request",
             "error_description": f"subject_token_type must be {TOKEN_TYPE_ID_TOKEN}"},
            status_code=400)

    audience = form.get("audience") or ""
    resource = form.get("resource") or ""
    if not audience or not resource:
        return JSONResponse(
            {"error": "invalid_target",
             "error_description": "audience and resource are both required"},
            status_code=400)

    try:
        subject = verify_subject_token(form.get("subject_token") or "", client_id)
    except ValueError as exc:
        event("exchange.refused", client=client_id, reason="subject", detail=str(exc))
        return JSONResponse(
            {"error": "invalid_grant", "error_description": str(exc)}, status_code=400)

    conn = connection_for(client_id, audience, resource)
    if conn is None:
        # The administrator has not approved this edge. Said plainly, because
        # the fix is a configuration change somebody has to go and make.
        event("exchange.refused", client=client_id, reason="no-connection",
              audience=audience, resource=resource)
        return JSONResponse(
            {"error": "invalid_target",
             "error_description": "no connection is configured from this "
                                  "application to that resource"},
            status_code=400)

    granted = list(conn["scopes"])
    if requested := (form.get("scope") or "").split():
        granted = [s for s in requested if s in conn["scopes"]]
        if not granted:
            event("exchange.refused", client=client_id, reason="scope",
                  requested=requested, allowed=conn["scopes"])
            return JSONResponse(
                {"error": "invalid_scope",
                 "error_description": "the connection does not carry that scope"},
                status_code=400)

    claims = {
        "iss": ISSUER,
        "sub": subject["sub"],
        "aud": audience,
        "client_id": client_id,
        "resource": resource,
        "scope": " ".join(granted),
        "jti": uuid.uuid4().hex,
        "iat": int(now()),
        "exp": int(now()) + JAG_TTL,
        # Who the employee is, in terms the receiving authority can act on. It
        # already knows its members by name; `sub` is a realm-local opaque id
        # and would need a directory lookup this service is not going to hold
        # open on its behalf.
        "tenant": "northwind",
    }
    for optional, key in (("preferred_username", "preferred_username"),
                          ("email", "email"), ("auth_time", "auth_time")):
        if subject.get(optional) is not None:
            claims[key] = subject[optional]

    assertion = jwt.encode(claims, SIGNING_KEY, algorithm="EdDSA",
                           headers={"typ": ID_JAG_TYP, "kid": KID})
    event("exchange.issued", client=client_id, sub=subject["sub"],
          who=subject.get("preferred_username"), audience=audience,
          resource=resource, scope=claims["scope"], jti=claims["jti"])
    return JSONResponse({
        "issued_token_type": TOKEN_TYPE_ID_JAG,
        "access_token": assertion,
        # RFC 8693: an issued token that is not an access token says so.
        "token_type": "N_A",
        "expires_in": JAG_TTL,
        "scope": claims["scope"],
    })


# ── Discovery ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"ok": True, "issuer": ISSUER, "connections": len(CONNECTIONS)}


@app.get("/jwks")
async def jwks() -> dict:
    return {"keys": [{**PUBLIC_JWK, "kid": KID, "use": "sig", "alg": "EdDSA"}]}


@app.get("/.well-known/openid-configuration")
async def discovery() -> dict:
    """Enough for a receiving authorization server to find the signing keys
    and satisfy itself about who issued an assertion."""
    return {
        "issuer": ISSUER,
        "jwks_uri": f"{ISSUER}/jwks",
        "token_endpoint": f"{ISSUER}/token",
        "grant_types_supported": [GRANT_TOKEN_EXCHANGE],
        "token_endpoint_auth_methods_supported": ["client_secret_basic",
                                                  "client_secret_post"],
        "subject_token_types_supported": [TOKEN_TYPE_ID_TOKEN],
        "requested_token_types_supported": [TOKEN_TYPE_ID_JAG],
        # Whose employees these are. A receiving authority checks this against
        # the provider its charter names before it trusts a single claim.
        "id_jag_identity_provider": IDP_ISSUER,
    }


# ── Administration ───────────────────────────────────────────────────────────

def require_admin(request: Request) -> str:
    """Dana, at Northwind's identity provider.

    Either a realm token for somebody in the administrator list, or the lab's
    seed token. Nothing about a connection is readable without one — the list
    of approved edges is itself a map of what the enterprise integrates."""
    raw = request.headers.get("authorization", "")
    presented = raw.split(" ", 1)[1] if raw.lower().startswith("bearer ") else ""
    if not presented:
        raise ValueError("no bearer token")
    if secrets.compare_digest(presented, ADMIN_TOKEN):
        return "seed"
    try:
        head = jwt.get_unverified_header(presented)
        for jwk_dict in idp_keys():
            if head.get("kid") and jwk_dict.get("kid") != head["kid"]:
                continue
            claims = jwt.decode(presented, jwt.PyJWK(jwk_dict).key,
                                algorithms=[head.get("alg", "RS256")],
                                issuer=IDP_ISSUER,
                                options={"verify_aud": False})
            who = claims.get("preferred_username") or claims.get("sub") or ""
            if who in ADMINS:
                return who
            raise ValueError(f"{who} does not administer this provider")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"token does not verify: {exc}")
    raise ValueError("token does not verify")


@app.get("/admin/connections")
async def list_connections(request: Request) -> JSONResponse:
    try:
        require_admin(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    return JSONResponse({"connections": list(CONNECTIONS.values())})


@app.post("/admin/connections")
async def add_connection(request: Request) -> JSONResponse:
    try:
        who = require_admin(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    doc = await request.json()
    for field in ("requesting_client", "audience", "resource"):
        if not doc.get(field):
            return JSONResponse({"error": f"{field} is required"}, status_code=400)
    scopes = doc.get("scopes") or []
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        return JSONResponse({"error": "scopes must be a list of strings"},
                            status_code=400)
    conn = {
        "id": doc.get("id") or uuid.uuid4().hex[:12],
        "requesting_client": doc["requesting_client"],
        "audience": doc["audience"],
        "resource": doc["resource"],
        "scopes": scopes,
        "enabled": bool(doc.get("enabled", True)),
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    CONNECTIONS[conn["id"]] = conn
    event("connection.configured", by=who, id=conn["id"],
          client=conn["requesting_client"], audience=conn["audience"],
          resource=conn["resource"], scopes=conn["scopes"])
    return JSONResponse(conn, status_code=201)


@app.delete("/admin/connections/{conn_id}")
async def drop_connection(conn_id: str, request: Request) -> JSONResponse:
    try:
        who = require_admin(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    if CONNECTIONS.pop(conn_id, None) is None:
        return JSONResponse({"error": "no such connection"}, status_code=404)
    event("connection.withdrawn", by=who, id=conn_id)
    return JSONResponse({"ok": True})


@app.on_event("startup")
async def boot() -> None:
    for entry in json.loads(os.environ.get("XAA_CLIENTS", "{}")).items():
        CLIENTS[entry[0]] = entry[1]
    for doc in json.loads(os.environ.get("XAA_SEED_CONNECTIONS", "[]")):
        doc.setdefault("id", uuid.uuid4().hex[:12])
        doc.setdefault("enabled", True)
        doc.setdefault("created", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        CONNECTIONS[doc["id"]] = doc
    event("ready", issuer=ISSUER, idp=IDP_ISSUER, kid=KID,
          clients=sorted(CLIENTS), connections=len(CONNECTIONS))
