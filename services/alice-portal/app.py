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

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from mcp_client import VaultClient

UMA_AS = os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000")
OWNER_TOKEN = os.environ.get("UMA_AS_OWNER_TOKEN", "owner-dev-portal")
VAULT_MCP = os.environ.get("VAULT_MCP_URL", "http://alice-vault-mcp:9020/mcp")
AUTH_MODE = os.environ.get("PORTAL_AUTH", "oidc")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "https://keycloak.uma.lab/realms/alice")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "alice-portal")
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
        server_metadata_url=f"{OIDC_ISSUER}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
        token_endpoint_auth_method="none",
    )


def owner_headers() -> dict:
    return {"Authorization": f"Bearer {OWNER_TOKEN}"}


def current_user(request: Request) -> str | None:
    if AUTH_MODE != "oidc":
        return "alice"
    return request.session.get("user")


def require_login(request: Request):
    if current_user(request) is None:
        return RedirectResponse(url="/login")
    return None


# --- Auth --------------------------------------------------------------------


@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for("auth_callback")).replace("http://", "https://")
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    request.session["user"] = userinfo.get("name") or userinfo.get("preferred_username", "Alice")
    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout(request: Request):
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
    return {"authenticated": True, "name": user, "auth": AUTH_MODE}


# --- Brokerage data (Alice's own vault, direct) ------------------------------


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
        r = await c.get(f"{UMA_AS}/owner/pending", headers=owner_headers())
    return JSONResponse(r.json())


@app.post("/api/agent/pending/{family}/decision")
async def agent_decision(family: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/pending/{family}/decision",
                         json=body, headers=owner_headers())
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/policies")
async def agent_policies(request: Request):
    if require_login(request):
        return JSONResponse({}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/policies", headers=owner_headers())
    return JSONResponse(r.json())


@app.put("/api/agent/policies/{tier_id}")
async def agent_update_policy(tier_id: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    body = await request.json()
    async with httpx.AsyncClient() as c:
        r = await c.put(f"{UMA_AS}/owner/policies/{tier_id}",
                        json=body, headers=owner_headers())
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/connections")
async def agent_connections(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/connections", headers=owner_headers())
    return JSONResponse(r.json())


@app.post("/api/agent/connections/{jkt}/revoke")
async def agent_revoke(jkt: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{UMA_AS}/owner/connections/{jkt}/revoke",
                         headers=owner_headers())
    return JSONResponse(r.json(), status_code=r.status_code)


@app.get("/api/agent/ledger")
async def agent_ledger(request: Request):
    if require_login(request):
        return JSONResponse([], status_code=401)
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{UMA_AS}/owner/ledger", headers=owner_headers())
    return JSONResponse(r.json())


@app.get("/api/agent/events")
async def agent_events(request: Request):
    async def stream():
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("GET", f"{UMA_AS}/owner/events",
                                headers=owner_headers()) as r:
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
