"""alice-portal — Alice's brokerage portal.

A first-party brokerage UI (dashboard, holdings, trade) with her account
controls under Settings. The agent-authorization surface — where she governs
what other people's agents may do with her accounts — lives at
Settings -> Security -> Agent Authorization: pending approvals, the terms her
authorization server dictates, and the audit ledger.

Alice reads and trades her own vault directly (she owns it). The gateway and
the grant loop exist for *other people's* agents. Agent-authorization data
comes from her authorization server's owner API; the browser never sees the
owner token — the portal proxies it.
"""

import os
import secrets as pysecrets
import time

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from mcp_client import VaultClient

UMA_AS = os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000")
VAULT_MCP = os.environ.get("VAULT_MCP_URL", "http://alice-vault-mcp:9020/mcp")
AUTH_MODE = os.environ.get("PORTAL_AUTH", "oidc")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "https://keycloak.uma.lab/realms/alice")
# Where *this process* reads the discovery document, as distinct from the
# issuer the browser is sent to and the `iss` an ID token must carry.
#
# Normally the same host answers both and this is just derived. They come
# apart when the browser reaches Keycloak somewhere this pod cannot follow —
# a Codespace forwards it to a github.dev address that is authenticated at
# the edge and served with a public certificate, while this pod trusts only
# the lab CA. Keycloak keeps `issuer` and `authorization_endpoint` pointing
# at the public origin and, with hostname-backchannel-dynamic, hands back
# request-derived URLs for the endpoints a server calls.
OIDC_METADATA_URL = os.environ.get(
    "OIDC_METADATA_URL", f"{OIDC_ISSUER}/.well-known/openid-configuration")
# The origin the *browser* knows this portal by, when that is not the origin
# the request arrives with. Empty means "ask the request", which is right
# whenever the browser reaches this service directly.
#
# It is not right behind a tunnel. A Codespace forwards 9010 from a
# github.dev address into the cluster, and what lands here says
# localhost:9010 — so a redirect URI built from the request names a host the
# browser cannot return to, and the authorization server rejects it as
# unregistered.
PORTAL_PUBLIC_URL = os.environ.get("PORTAL_PUBLIC_URL", "").rstrip("/")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "meridian-portal")
# Whose portal this instance is. One per owner: the authority, the identity
# provider and the vault below are all hers, and nothing else here differs
# between one owner's instance and another's.
OWNER = os.environ.get("UMA_PORTAL_OWNER", "alice")
SESSION_SECRET = os.environ.get("PORTAL_SESSION_SECRET", "dev-session-secret")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="alice-portal")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=True)
vault = VaultClient(VAULT_MCP)

oauth = OAuth()
if AUTH_MODE == "oidc":
    oauth.register(
        name="keycloak",
        client_id=OIDC_CLIENT_ID,
        server_metadata_url=OIDC_METADATA_URL,
        client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
        token_endpoint_auth_method="none",
    )

# Alice's OIDC tokens, held server-side (Keycloak tokens overflow a cookie);
# the session cookie carries only an opaque reference. The owner API sees her
# actual access token — there is no static portal credential.
TOKENS: dict[str, dict] = {}


def _store_tokens(request: Request, token: dict) -> None:
    sid = request.session.get("sid") or pysecrets.token_urlsafe(16)
    request.session["sid"] = sid
    TOKENS[sid] = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": token.get("expires_at")
        or time.time() + token.get("expires_in", 300),
    }


async def owner_token(request: Request) -> str | None:
    """Alice's current access token, refreshed against Keycloak when stale."""
    tok = TOKENS.get(request.session.get("sid", ""))
    if tok is None:
        return None
    if tok["expires_at"] > time.time() + 15:
        return tok["access_token"]
    if not tok.get("refresh_token"):
        return None
    metadata = await oauth.keycloak.load_server_metadata()
    async with httpx.AsyncClient() as c:
        r = await c.post(
            metadata["token_endpoint"],
            data={"grant_type": "refresh_token",
                  "refresh_token": tok["refresh_token"],
                  "client_id": OIDC_CLIENT_ID},
        )
    if r.status_code != 200:
        return None
    fresh = r.json()
    tok.update(
        access_token=fresh["access_token"],
        refresh_token=fresh.get("refresh_token", tok["refresh_token"]),
        expires_at=time.time() + fresh.get("expires_in", 300),
    )
    return tok["access_token"]


async def owner_headers(request: Request) -> dict:
    token = await owner_token(request)
    return {"Authorization": f"Bearer {token}"} if token else {}


def current_user(request: Request) -> str | None:
    if AUTH_MODE != "oidc":
        return OWNER
    # A signed cookie can outlive the server-side token store (portal
    # restart): a session without live tokens is not a login.
    if request.session.get("sid") not in TOKENS:
        return None
    return request.session.get("user")


def require_login(request: Request):
    if current_user(request) is None:
        return RedirectResponse(url="/login")
    return None


# --- Auth --------------------------------------------------------------------


def _callback_url(request: Request) -> str:
    """Where the authorization server should send the browser back to.

    Must match a redirect URI registered on the client, and must be somewhere
    the browser can actually reach — which is not necessarily the host this
    process sees the request on.
    """
    if PORTAL_PUBLIC_URL:
        return f"{PORTAL_PUBLIC_URL}/auth/callback"
    return str(request.url_for("auth_callback")).replace("http://", "https://")


@app.get("/auth/login")
async def login(request: Request):
    return await oauth.keycloak.authorize_redirect(request, _callback_url(request))


@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    # Whoever signed in, never a name this process assumed. One image serves
    # any owner; the only thing that says which is the token that came back.
    request.session["user"] = (userinfo.get("name")
                               or userinfo.get("preferred_username")
                               or OWNER)
    _store_tokens(request, token)
    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout(request: Request):
    TOKENS.pop(request.session.get("sid", ""), None)
    request.session.clear()
    return RedirectResponse(url="/login")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "auth": AUTH_MODE}


@app.get("/api/me")
async def me(request: Request):
    user = current_user(request)
    if user is None:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "name": user, "owner": OWNER,
            "auth": AUTH_MODE}


# --- Brokerage data (this owner's own vault, direct) -------------------------


def _enrich(positions: list[dict]) -> dict:
    total_mv = sum(p["market_value"] for p in positions)
    total_cb = sum(p["cost_basis"] for p in positions)
    for p in positions:
        p["gain"] = round(p["market_value"] - p["cost_basis"], 2)
        p["gain_pct"] = round((p["gain"] / p["cost_basis"] * 100) if p["cost_basis"] else 0, 2)
        p["weight"] = round((p["market_value"] / total_mv * 100) if total_mv else 0, 2)
        p["price"] = round(p["market_value"] / p["quantity"], 2) if p.get("quantity") else 0
    return {
        "total_value": round(total_mv, 2),
        "total_cost": round(total_cb, 2),
        "total_gain": round(total_mv - total_cb, 2),
        "total_gain_pct": round(((total_mv - total_cb) / total_cb * 100) if total_cb else 0, 2),
        "positions": positions,
    }


@app.get("/api/portfolio")
async def portfolio(request: Request):
    if (r := require_login(request)):
        return JSONResponse({"error": "auth"}, status_code=401)
    data = await vault.call_tool("get_positions")
    enriched = _enrich(data["positions"])
    enriched["as_of"] = data["as_of"]
    return enriched


@app.get("/api/transactions")
async def transactions(request: Request, account: str = "brokerage-main"):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    return await vault.call_tool("get_transactions", {"account": account})


@app.post("/api/trade")
async def trade(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    result = await vault.call_tool(
        "execute_trade",
        {"symbol": body["symbol"], "side": body["side"], "quantity": int(body["quantity"])},
    )
    return result


# --- Agent authorization (proxied owner API; token stays server-side) --------


@app.get("/api/agent/pending")
async def agent_pending(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/pending", headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/pending/{family}/decision")
async def agent_decision(family: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/pending/{family}/decision",
                         json=body, headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/resources")
async def agent_resources(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/resources", headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/resource-servers")
async def agent_resource_servers(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/resource-servers",
                        headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/resource-servers/decision")
async def agent_decide_resource_server(request: Request):
    """Her answer about a resource server: approve one that introduced
    itself, or withdraw one she had allowed.

    The client_id travels in the body rather than the path. A resource server
    that registered itself is identified by its origin — an https URL — and a
    URL inside a path segment survives neither percent-decoding nor a proxy
    that normalises `//`.
    """
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/resource-servers/decision",
                         json={"client_id": body.get("client_id"),
                               "decision": body.get("decision")},
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/policies")
async def agent_policies(request: Request):
    if require_login(request):
        return JSONResponse({}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/policies", headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/policies")
async def agent_create_policy(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/policies", json=body,
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.delete("/api/agent/policies/{tier_id}")
async def agent_delete_policy(tier_id: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{UMA_AS}/owner/policies/{tier_id}",
                           headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/operators")
async def agent_operators(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/operators",
                        headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/operators/{action}")
async def agent_operator_action(action: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    if action not in ("block", "unblock"):
        return JSONResponse({"error": "unknown action"}, status_code=404)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/operators/{action}", json=body,
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/policy-vocabulary")
async def agent_policy_vocabulary(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/policy-vocabulary",
                        headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.put("/api/agent/policies/{tier_id}")
async def agent_update_policy(tier_id: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.put(f"{UMA_AS}/owner/policies/{tier_id}",
                        json=body, headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/organization")
async def agent_organization(request: Request):
    if require_login(request):
        return JSONResponse({"enrolled": False}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/organization",
                        headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/organization/preview")
async def agent_organization_preview(request: Request):
    """What an enrolment code would commit her to, before it does.

    Proxied like everything else here — the browser never holds her token —
    and separate from the join below on purpose. Two calls, because the
    answer to the first is the thing she is being asked to consent to.
    """
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/organization/preview", json=body,
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/organization")
async def agent_join_organization(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/organization", json=body,
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/organization/decline")
async def agent_decline_invitation(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/organization/decline",
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/joint")
async def agent_joint(request: Request):
    """The accounts she holds jointly with somebody else."""
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/joint",
                        headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/joint/preview")
async def agent_joint_preview(request: Request):
    """What a mandate would commit her to, before it does.

    Separate from the join below for the reason the organization's preview
    is: the answer to this is the thing she is being asked to agree to, and
    an endpoint that previewed and joined in one call would be asking her to
    agree to something she had not been shown.
    """
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/joint/preview", json=await request.json(),
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/joint")
async def agent_join_mandate(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/joint", json=await request.json(),
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.delete("/api/agent/joint/{account}")
async def agent_leave_mandate(account: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{UMA_AS}/owner/joint/{account}",
                           headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.delete("/api/agent/organization")
async def agent_leave_organization(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{UMA_AS}/owner/organization",
                           headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/connections")
async def agent_connections(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/connections", headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/agent/connections/{jkt}/revoke")
async def agent_revoke(jkt: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/connections/{jkt}/revoke",
                         headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/ledger")
async def agent_ledger(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    # `?handle=` narrows the record to one agent's trajectory. Forwarded
    # rather than filtered here: the portal holds no authority and no state,
    # and a filter it applied would be one the owner API could not vouch for.
    params = {"handle": h} if (h := request.query_params.get("handle")) else None
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/ledger", params=params,
                        headers=await owner_headers(request))
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/events")
async def agent_events(request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)

    async def stream():
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("GET", f"{UMA_AS}/owner/events",
                                headers=await owner_headers(request)) as r:
                async for chunk in r.aiter_raw():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


# --- Static SPA --------------------------------------------------------------


@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/")
async def index(request: Request):
    if current_user(request) is None:
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


class RevalidatingStatic(StaticFiles):
    """Static files the browser must revalidate before reusing.

    Without a `Cache-Control` header a browser is free to apply heuristic
    freshness — roughly a tenth of the age of the file — and serve a cached
    copy without asking. In a lab whose images are rebuilt while somebody has
    the page open, that shows up as a console running new JavaScript against
    an old stylesheet, which looks like a layout bug and is not one.
    `no-cache` still allows a 304 against the ETag already sent, so this costs
    a conditional request rather than a transfer.
    """

    def file_response(self, *args, **kw):
        r = super().file_response(*args, **kw)
        r.headers["Cache-Control"] = "no-cache"
        return r


app.mount("/static", RevalidatingStatic(directory=STATIC_DIR), name="static")
