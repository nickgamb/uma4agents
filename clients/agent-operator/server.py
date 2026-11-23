"""Sterling & Vance — the public web presence of the firm that operates Bob's agent.

Both of the identity conventions this lab adopts assume the requesting side has
somewhere on the web that speaks for it, and neither works without one:

  /agent.json
      A Client ID Metadata Document (draft-ietf-oauth-client-id-metadata-document),
      the mechanism MCP now prefers over Dynamic Client Registration. Alice's
      approval dialog resolves this to show an operator and a policy URI
      instead of a bare key thumbprint. Display metadata only — her AS still
      keys the connection by the agent's key or its verified issuer, so
      nothing here can widen access.

  /.well-known/http-message-signatures-directory
      A Web Bot Auth key directory (draft-meunier-http-message-signatures-directory):
      a JWKS of the keys this operator's agents sign with. A resource that has
      never met this agent can fetch it and learn the key belongs to a
      published operator — which is the RqP != RO cold-start problem, since by
      definition there is no prior relationship to lean on.

  /atf
      The operator's Agentic Trust Framework conformance statement, in the
      shape ATF's CONFORMANCE.md gives for "ATF Compatible". Its agents' metadata
      documents point at it, beside the maturity level the operator has put
      each class of agent at — the operator's own ladder, which an owner's
      authorization server reads and may only tighten on. See docs/AUTONOMY.md.

  /agents/<class>.json
      One metadata document per class of agent this firm runs, when it runs
      more than one. ATF levels are per agent: a firm's research assistant and
      its advisory agent are at different rungs of its own ladder, and each is
      a client with its own `client_id`.

A real operator publishes keys it already holds, and that is the shape here:
AGENT_OPERATOR_KEYS_FILE names a JWKS this process reads at startup and only
serves. POST /register remains as a lab path for the single-process stack,
whose agent keys are generated per run — and is refused outright once a
published file is configured, so the two modes cannot be mixed.

The distinction matters more than it looks. A directory held only in memory
and filled in by whoever happened to call is a directory that empties on
restart and disagrees with itself the moment there are two of these
processes — an agent registers with one, a resource asks the other, and the
key it needs is missing. Seeding from a file makes this service hold no
authoritative state at all, which is what makes running several of them
correct. The way to make a service horizontally scalable is usually to stop
it holding state, not to replicate the state.
"""

import hmac
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ORIGIN = os.environ.get("AGENT_OPERATOR_ORIGIN", "https://agent.uma.lab")
NAME = os.environ.get("AGENT_OPERATOR_NAME", "Sterling & Vance — Advisory Agent")
KEYS_FILE = os.environ.get("AGENT_OPERATOR_KEYS_FILE")
# Set wherever the directory speaks for an owner: a key it lists is how her
# authorization server recognises her own agents, so publishing one takes a
# credential. Unset only for a directory nothing grants standing on.
REGISTER_TOKEN = os.environ.get("AGENT_OPERATOR_REGISTER_TOKEN")
# Where this operator has put its default agent on its own ATF ladder. Unset
# means the operator says nothing about it, which is not the same as saying
# its agent is an intern — and is how every operator that has not heard of
# ATF looks.
ATF_LEVEL = os.environ.get("AGENT_OPERATOR_ATF_LEVEL")
ATF_CONFORMANCE = os.environ.get("AGENT_OPERATOR_ATF_CONFORMANCE", "compatible")
ATF_VERSION = "0.9.0"
# Further classes of agent, each its own client: {"research": {"name": …,
# "atf_level": "intern"}}. Lab data rather than a registry — a firm knows
# which agents it runs.
try:
    CLASSES: dict[str, dict] = json.loads(
        os.environ.get("AGENT_OPERATOR_CLASSES") or "{}")
except ValueError:
    CLASSES = {}

app = FastAPI(title="agent-operator")

# keyid -> JWK. Seeded from the published file; added to by /register.
KEYS: dict[str, dict] = {}


def load_published_keys() -> int:
    """Read the operator's published JWKS, if it has one.

    A missing or malformed file is not fatal: the directory is a discovery
    aid, never an authorization input, so serving an empty one is a
    degradation rather than a failure. Saying so out loud is the point —
    a service that refused to start over this would be treating discovery as
    though it were trust.
    """
    if not KEYS_FILE:
        return 0
    try:
        with open(KEYS_FILE) as f:
            published = json.load(f)
    except (OSError, ValueError) as exc:
        print(json.dumps({"event": "agent_keys.unreadable", "path": KEYS_FILE,
                          "error": str(exc)[:120]}), flush=True)
        return 0
    for jwk in published.get("keys", []):
        if kid := jwk.get("kid"):
            KEYS[kid] = jwk
    print(json.dumps({"event": "agent_keys.published_loaded",
                      "path": KEYS_FILE, "keys": len(KEYS)}), flush=True)
    return len(KEYS)


@app.on_event("startup")
async def seed_directory() -> None:
    load_published_keys()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "keys": len(KEYS)}


def metadata(path: str, name: str, atf_level: str | None) -> dict:
    """One CIMD document. `client_id` MUST equal the URL it is served from —
    that self-reference is what stops one site publishing metadata about
    another's client, and Alice's AS rejects the document if it disagrees."""
    doc = {
        "client_id": f"{ORIGIN}{path}",
        "client_name": name,
        "client_uri": ORIGIN,
        "policy_uri": f"{ORIGIN}/privacy",
        "tos_uri": f"{ORIGIN}/terms",
        "contacts": ["advisory-ops@sterling-vance.example"],
        "software_id": "uma4agents-agent-shim",
    }
    if atf_level:
        # The operator's own ladder. Its statement about its own agent: an
        # owner's authority reads it and may only ever tighten on it.
        doc["atf"] = {"version": ATF_VERSION, "maturity_level": atf_level,
                      "conformance": ATF_CONFORMANCE,
                      "statement_uri": f"{ORIGIN}/atf"}
    return doc


@app.get("/agent.json")
async def client_id_metadata() -> JSONResponse:
    return JSONResponse(metadata("/agent.json", NAME, ATF_LEVEL))


@app.get("/agents/{cls}.json")
async def class_metadata(cls: str) -> JSONResponse:
    """A further class of agent this firm runs, as its own client."""
    entry = CLASSES.get(cls)
    if not isinstance(entry, dict):
        return JSONResponse({"error": "no such agent class"}, status_code=404)
    return JSONResponse(metadata(f"/agents/{cls}.json",
                                 entry.get("name") or f"{NAME} ({cls})",
                                 entry.get("atf_level")))


@app.get("/atf")
async def atf_statement() -> JSONResponse:
    """The firm's ATF conformance statement — ATF's own template, as data.

    Self-assessed, because that is what "ATF Compatible" is, and an owner's
    authority treats it accordingly: it is shown to her and credited with
    nothing. The element scores are this lab's honest reading of what the
    stack around this operator demonstrates, not a claim about any real firm.
    """
    return JSONResponse({
        "organization": NAME.split(" — ")[0],
        "implementation": NAME,
        "atf_version": ATF_VERSION,
        "conformance": ATF_CONFORMANCE,
        "target_maturity_levels": {"/agent.json": ATF_LEVEL, **{
            f"/agents/{k}.json": (v or {}).get("atf_level")
            for k, v in CLASSES.items()}},
        "elements": {"identity": "4/5", "behavior": "2/5",
                     "data_governance": "1/5", "segmentation": "4/5",
                     "incident_response": "3/5"},
        "notes": "lab operator; see docs/AUTONOMY.md for the crosswalk",
    })


@app.get("/.well-known/http-message-signatures-directory")
async def signatures_directory() -> JSONResponse:
    """Web Bot Auth key directory: a JWKS under a dedicated media type."""
    return JSONResponse(
        {"keys": list(KEYS.values())},
        media_type="application/http-message-signatures-directory+json",
    )


@app.post("/register")
async def register(request: Request) -> JSONResponse:
    """Lab-only: an agent publishes the key it is about to sign with.

    Real operators publish keys they already hold, which is what
    AGENT_OPERATOR_KEYS_FILE is. This exists because the toy stack generates
    its agent keys per run and something has to publish them. It is
    authenticated by AGENT_OPERATOR_REGISTER_TOKEN wherever that is set,
    because a key listed here is how an owner's authorization server
    recognises her own agents: an open directory lets any agent claim to be
    one of them.

    **Refused once the operator is seeded from a file**, and that is the
    interesting line rather than a safety rail. This endpoint writes to one
    process's memory. With a single process that is merely untidy; with more
    than one it is wrong in a way nothing reports — the registration lands on
    one replica, a resource server asks another, the key is missing, and an
    agent that did everything right drops an assurance level about half the
    time. Refusing here is what makes `replicas: 2` a true statement instead
    of an aspiration: a seeded directory is read-only, identical everywhere,
    and cannot drift.
    """
    if KEYS_FILE:
        return JSONResponse(
            {"registered": False,
             "error": "this operator publishes keys it already holds",
             "detail": ("AGENT_OPERATOR_KEYS_FILE is set, so the directory is "
                        "read-only and identical across replicas. Provision "
                        "the key into that document instead.")},
            status_code=409)
    if REGISTER_TOKEN:
        given = request.headers.get("authorization", "")
        if not hmac.compare_digest(given, f"Bearer {REGISTER_TOKEN}"):
            return JSONResponse({"registered": False,
                                 "error": "this directory publishes keys only "
                                          "for callers holding its registration "
                                          "credential"}, status_code=401)
    body = await request.json()
    jwk = body.get("jwk") or {}
    keyid = body.get("keyid") or jwk.get("kid")
    if not keyid or not jwk:
        return JSONResponse({"registered": False,
                             "error": "keyid and jwk required"}, status_code=400)
    KEYS[keyid] = {**jwk, "kid": keyid}
    print(json.dumps({"event": "agent_key.published", "keyid": keyid}), flush=True)
    return JSONResponse({"registered": True, "keyid": keyid, "keys": len(KEYS)})
