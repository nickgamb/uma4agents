"""org-console — the administrator's surface, hosted by Meridian.

The shape is the same as `alice-portal` and the resemblance is the argument:
a portal is a client of an authority, holds no policy and no state of its
own, and proxies the token so the browser never sees it. Alice's portal is a
client of Alice's authority; this is a client of the organization's. One
pattern, two parties, and nothing here can reach a member's authority at all.

Meridian hosts it, in the way a productivity suite hosts an admin console for
the companies whose staff use it. Meridian is not the organization and is not
the owner: it runs the resource server, the gateway, and this console, and it
is the party with the least authority in the picture.
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

ORG_AUTHORITY = os.environ.get("ORG_AUTHORITY_INTERNAL", "http://org-authority:9040")
AUTH_MODE = os.environ.get("CONSOLE_AUTH", "oidc")
OIDC_ISSUER = os.environ.get(
    "OIDC_ISSUER", "https://keycloak.uma.lab/realms/northwind")
OIDC_METADATA_URL = os.environ.get(
    "OIDC_METADATA_URL", f"{OIDC_ISSUER}/.well-known/openid-configuration")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "meridian-org-console")
CONSOLE_PUBLIC_URL = os.environ.get("CONSOLE_PUBLIC_URL", "").rstrip("/")
SESSION_SECRET = os.environ.get("CONSOLE_SESSION_SECRET", "dev-session-secret")
# Only for a stack with no identity provider — the acceptance containers, and
# a laptop run with PORTAL_AUTH=none. Never set where OIDC is configured.
STATIC_ADMIN_TOKEN = os.environ.get("ORG_ADMIN_TOKEN", "")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="org-console")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=True)

oauth = OAuth()
if AUTH_MODE == "oidc":
    oauth.register(
        name="keycloak",
        client_id=OIDC_CLIENT_ID,
        server_metadata_url=OIDC_METADATA_URL,
        client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
        token_endpoint_auth_method="none",
    )

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


async def admin_token(request: Request) -> str | None:
    if AUTH_MODE != "oidc":
        return STATIC_ADMIN_TOKEN or None
    tok = TOKENS.get(request.session.get("sid", ""))
    if tok is None:
        return None
    if tok["expires_at"] > time.time() + 15:
        return tok["access_token"]
    if not tok.get("refresh_token"):
        return None
    metadata = await oauth.keycloak.load_server_metadata()
    async with httpx.AsyncClient() as c:
        r = await c.post(metadata["token_endpoint"],
                         data={"grant_type": "refresh_token",
                               "refresh_token": tok["refresh_token"],
                               "client_id": OIDC_CLIENT_ID})
    if r.status_code != 200:
        return None
    fresh = r.json()
    tok.update(access_token=fresh["access_token"],
               refresh_token=fresh.get("refresh_token", tok["refresh_token"]),
               expires_at=time.time() + fresh.get("expires_in", 300))
    return tok["access_token"]


async def admin_headers(request: Request) -> dict:
    token = await admin_token(request)
    return {"Authorization": f"Bearer {token}"} if token else {}


def current_admin(request: Request) -> str | None:
    if AUTH_MODE != "oidc":
        return "console"
    if request.session.get("sid") not in TOKENS:
        return None
    return request.session.get("user")


def require_login(request: Request):
    return None if current_admin(request) is not None else RedirectResponse(url="/login")


def _callback_url(request: Request) -> str:
    if CONSOLE_PUBLIC_URL:
        return f"{CONSOLE_PUBLIC_URL}/auth/callback"
    return str(request.url_for("auth_callback")).replace("http://", "https://")


@app.get("/auth/login")
async def login(request: Request):
    return await oauth.keycloak.authorize_redirect(request, _callback_url(request))


@app.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    request.session["user"] = (userinfo.get("name")
                               or userinfo.get("preferred_username")
                               or "Administrator")
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
    admin = current_admin(request)
    if admin is None:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "name": admin, "auth": AUTH_MODE}


# --- Proxied admin API -------------------------------------------------------
#
# One passthrough rather than a handler per endpoint. There is no logic to put
# in between: the console holds no policy, decides nothing, and its only job
# is to keep the administrator's token out of the browser — so a proxy that
# forwards method, path and body, and returns the authority's own status and
# message, is exactly the whole of it. The authority's refusals reach the
# editor unedited, which is what makes a rejected charter teach something.

ALLOWED = ("org", "charter", "members", "invites", "roles", "activity",
           "break-glass", "join-code")


@app.api_route("/api/org/{path:path}",
               methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    if require_login(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    # Same rule as the authority's own proxy: the first segment names the
    # surface, and no segment may climb out of `/admin/`. A relative segment
    # that survives to a URL library is a way out of the allow-list.
    segments = [x for x in path.split("/") if x not in ("", ".")]
    if not segments or segments[0] not in ALLOWED or ".." in segments:
        return JSONResponse({"error": "unknown endpoint"}, status_code=404)
    path = "/".join(segments)
    body = await request.body()
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.request(
            request.method, f"{ORG_AUTHORITY}/admin/{path}",
            content=body or None,
            headers={**await admin_headers(request),
                     **({"content-type": "application/json"} if body else {})})
    try:
        return JSONResponse(r.json(), status_code=r.status_code)
    except ValueError:
        return JSONResponse({"error": r.text}, status_code=r.status_code)


@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/")
async def index(request: Request):
    if current_admin(request) is None:
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
