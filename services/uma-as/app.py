"""uma-as — the UMA-for-agents authorization service (reference implementation).

Implements the four-beat grant loop from docs/PROTOCOL.md:

  challenge (ticket via /perm) -> attempt (/token: need_info + dictated terms)
  -> commit (signed intent contract) -> grant (PoP-bound RPT)

with UMA 2.0's request_submitted pending state for Alice's ask-me tier, an
owner API for the portal (pending approvals, tier policy, ledger), and one
structured log line per protocol event (ticket family = correlation id).

State is in-memory by design: `make reset` rewinds the story.
"""

import asyncio
import base64
import hashlib
import calendar
import html
import json
import logging
import os
import secrets
import sys
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from jwt.algorithms import OKPAlgorithm

import assurance
import joint
import org
import uma4a_joint
import policy
import store

ISSUER = os.environ.get("UMA_AS_ISSUER", "https://alice-as.uma.lab")
# The host a signature over a request to this server has to cover. Taken
# from the issuer so the two cannot drift apart.
AS_AUTHORITY = ISSUER.split("://", 1)[-1].rstrip("/")
KEY_PATH = os.environ.get("UMA_AS_SIGNING_KEY", "/keys/uma-as-ed25519.pem")
# The owner authenticates with her OIDC token (Keycloak); the AS validates
# it against the realm's published keys. No static owner credential exists.
OWNER_ISSUER = os.environ.get(
    "UMA_AS_OWNER_ISSUER", "https://keycloak.uma.lab/realms/alice")
# Where to read her identity provider's metadata, as distinct from the issuer
# her tokens must claim. Normally the same origin answers both. They come
# apart when her browser reaches it somewhere this process cannot follow — a
# tunnelled deployment gives the browser a public address while this pod has
# only the cluster network — and the issuer in the token is then the address
# the *browser* used, not the one the keys were fetched from.
OWNER_METADATA_URL = os.environ.get(
    "UMA_AS_OWNER_METADATA_URL",
    f"{OWNER_ISSUER}/.well-known/openid-configuration")
# Whose authority this is.
#
# An authorization server belongs to one owner. `UMA_AS_OWNER` names her, and
# every other owner is refused at the door rather than filtered out later —
# on her laptop, in a container, at the edge, the answer to "may I read
# somebody else's policy" is no before the question reaches the store.
#
# Unset, the server falls back to a default owner. That is a convenience for
# tests and for a single-owner lab, not a deployment shape: the many-owner
# case is one *resource server* holding many people's accounts, each governed
# by an authority of her own, which is what k8s/base and docker-compose run.
#
# The store is partitioned by owner regardless, and that is what makes an
# owner's state a clean cut — the reason her authority can move somewhere she
# controls without the grant loop noticing.
SERVED_OWNER = os.environ.get("UMA_AS_OWNER") or None
# Retained for the paths that need *an* owner before a request has named one:
# startup seeding, the resource pull, and the compose stack's fixtures.
DEFAULT_OWNER = SERVED_OWNER or os.environ.get("UMA_AS_DEFAULT_OWNER", "alice")
# Which owner the configured device key belongs to. See
# require_owner_signature: the signature proves a holder, this says whose.
OWNER_KEY_OWNER = os.environ.get("UMA_AS_OWNER_KEY_OWNER", DEFAULT_OWNER)

# Where an enrolment code is redeemed.
#
# One organization, named by configuration, because an enrolment code is the
# only thing the owner is asked for and a code says nothing about who issued
# it. A deployment with many organizations needs a directory to resolve that
# — a real question, and not one this lab pretends to have answered. What is
# demonstrated here is the layer, not its discovery.
ORG_ISSUER = os.environ.get("UMA_AS_ORG_ISSUER", "")
# The address the organization posts notices back to. Its own view of this
# server, which is not necessarily the issuer an agent is challenged with.
ORG_CALLBACK = os.environ.get("UMA_AS_ORG_CALLBACK", ISSUER)


def st(owner: str):
    """This owner's state. The only way to reach the store."""
    return STORE.owner(owner)


def serves(owner: str) -> bool:
    return SERVED_OWNER is None or owner == SERVED_OWNER


# Tickets are minted by this server, so they can carry the owner they belong
# to. A multi-tenant deployment needs that: a ticket arrives with no session
# and no token, and there is nothing else on the request that says whose
# negotiation it indexes. A single-owner deployment does not need it and pays
# nothing for it.
def _enc_owner(owner: str) -> str:
    return base64.urlsafe_b64encode(owner.encode()).decode().rstrip("=")


def split_ticket(ticket: str | None) -> tuple[str | None, str]:
    """(owner, the store's ticket). Owner is None if the ticket is unmarked,
    which is what a ticket minted before this looked like."""
    head, sep, rest = (ticket or "").partition("~")
    if not sep:
        return None, ticket or ""
    try:
        return base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)).decode(), rest
    except Exception:                                          # noqa: BLE001
        return None, ticket or ""
OWNER_AUDIENCES = set(
    os.environ.get("UMA_AS_OWNER_CLIENTS", "meridian-portal").split(","))

# How the owner proves she is the owner, to her own authorization server.
#
#   oidc       she signs in to an identity provider and the AS validates the
#              token against its published keys. Right for a deployment that
#              already has one, and the default.
#   local-key  she holds an Ed25519 key and signs her owner-API requests with
#              it (RFC 9421 — the same profile agents use for proof-of-
#              possession, pointed at the owner). No identity provider, no
#              static credential, nothing to stand up.
#
# Both, comma-separated, is the interesting configuration and the one the
# reference stack runs: `oidc,local-key`. A person has more than one way to
# reach her own things — a browser on her laptop, an app on her phone, a
# personal AI holding a key — and the profile should not force her to pick
# one. Each credential is independently sufficient and independently
# revocable; the second is not a fallback for the first.
#
# The key mode exists because OIDC is the one piece of this profile that
# cannot go anywhere small. An authority meant to be personal should not
# require her to operate an identity provider before she can answer a single
# request. The verifying code is the same either way; only the credential is
# different.
OWNER_AUTH = tuple(
    m.strip().lower()
    for m in os.environ.get("UMA_AS_OWNER_AUTH", "oidc").split(",")
    if m.strip()
)
# Her public key, in local-key mode: a path to an Ed25519 public key PEM.
OWNER_KEY_PATH = os.environ.get("UMA_AS_OWNER_KEY", "/keys/owner-ed25519.pub")
# The authority this AS reconstructs an owner signature base against. Taken
# from configuration, never from the request — an authority the caller can set
# is not an authority. Defaults to the host part of this AS's own issuer.
OWNER_EXPECTED_AUTHORITY = os.environ.get(
    "UMA_AS_OWNER_AUTHORITY", ISSUER.split("://", 1)[-1].split("/", 1)[0])
PAT_TTL = 3600
# Registration is declarative: this AS *reads* the RS's published metadata —
# public structure from the RFC 9728 document, owner-bound instances from the
# protected owner-resources endpoint — and materializes its registry from it.
# Classic FedAuthz push registration (/rreg) is gone from this line; the
# measured comparison lives on the `legacy/rreg-baseline` branch, and rec 5 in
# FINDINGS.md is what it produced. One registry, one writer.
# The owner-proffered terms + signed agreement follow the MyTerms pattern
# (IEEE 7012): the individual proffers machine-readable terms from her own
# roster; the counterparty agrees; both sides keep a record. The URN is ours —
# a MyTerms-shaped profile for agentic access terms, not a claim of
# conformance to the IEEE document's schema.
AGREEMENT_FORMAT = "urn:uma4agents:format:myterms-agreement-v1+jws"

# The enterprise half, when a member's organization federates identity.
#
# An ID-JAG (draft-ietf-oauth-identity-assertion-authz-grant, also called
# Cross App Access) is an identity provider's assertion that a named employee
# is behind a named application, and that an administrator approved that
# application reaching a named resource. It is not an access token and it
# carries no entitlement — which is exactly why it can be a *claim* here
# rather than a competing grant. It answers the question this server cannot
# answer for itself, and then stops.
ID_JAG_FORMAT = "urn:ietf:params:oauth:token-type:id-jag"
ID_JAG_TYP = "oauth-id-jag+jwt"
ID_JAG_CLAIM = "urn:ietf:params:oauth:token-type:id-jag"
# What the agent should name as the resource when it goes to get one. The
# same value the resource server publishes as its own identifier.
RS_RESOURCE_URI = os.environ.get("UMA_AS_RS_RESOURCE_URI",
                                 "https://gateway.uma.lab/mcp")
# Spent assertions, by `jti`, until they expire. An ID-JAG is minted for one
# negotiation and one authorization server; replaying one is not a thing a
# well-behaved client does.
_ID_JAG_SPENT: dict[str, float] = {}
AGREEMENT_CLAIM = "urn:uma4agents:claim:myterms-agreement"
TICKET_TTL = 300
# How long a held "ask-me" ticket stays valid. The demo's own premise is that
# Alice may be asleep, so ten minutes was never right — and it is only safe to
# lengthen because the requesting side no longer holds a call open across it
# (the shim hands the wait up as an MCP input_required and resumes).
PENDING_TTL = int(os.environ.get("UMA_AS_PENDING_TTL", 3600))
POLL_INTERVAL = 3

log = logging.getLogger("uma-as")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")


def now() -> float:
    return time.time()


def s256(data: bytes) -> str:
    return "s256:" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def event(name: str, corr: str | None = None, **details) -> None:
    log.info(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": name,
                "corr": corr,
                "actor": "uma-as",
                "details": details,
            }
        )
    )


def load_or_create_key() -> Ed25519PrivateKey:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return key


SIGNING_KEY = load_or_create_key()
KID = "uma-as-1"

app = FastAPI(title="uma-as")

# ---------------------------------------------------------------------------
# State.
#
# Everything the grant loop remembers lives behind STORE (see store.py):
# negotiations and the tickets that index them, issued RPTs, standing
# connections, the ledger, Alice's tiers, the resource servers she has
# authorized. Two backends — in-process for the compose stack, Postgres when
# this service runs replicated — because at more than one replica a
# module-level dict is not merely slower, it is wrong: a ticket minted here
# is unknown there, and a single-use burn stops being single-use.
#
# The negotiation record is keyed by its *family* and lives for the whole
# negotiation; the ticket table is only a rotating index into it. Each
# presentation consumes the current ticket (UMA 2.0 single-use rule) and, if
# the negotiation continues, a fresh ticket is indexed to the same family.
#
# Keying the record by the ticket instead — the obvious first design — makes
# the record invisible between the pop and the re-insert, so a concurrent
# /owner/pending misses it and /owner/pending/{family}/decision 404s on a
# negotiation that plainly exists. The family is the stable identity here;
# the ticket is a credential for it.
#
# RESOURCES stays here, per process, and deliberately: it is a *derived*
# cache of what the resource server publishes, re-pullable at any time from
# the authoritative copy, so replicas converging separately is correct rather
# than merely tolerable. Standing relationships are the opposite — one wrong
# answer there is an access-control failure — which is the line between the
# two.
# ---------------------------------------------------------------------------
# How much the requesting side may write about itself. Small on purpose: this
# is a sentence for a person to read in an approval dialog, not a document.
MAX_REASON = int(os.environ.get("UMA_AS_MAX_REASON", "512"))

# How far back a rule about an agent's recent behaviour looks. One window for
# all of them, so a rule reads "recently" and the deployment says how long that
# is, rather than every rule carrying its own duration.
TRAJECTORY_WINDOW = os.environ.get("UMA_AS_TRAJECTORY_WINDOW", "7d")

STORE: store.Store = store.make_store()
RESOURCES: dict[str, dict] = {}


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint (OKP profile)."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
        separators=(",", ":"), sort_keys=True,
    )
    return "jkt:" + base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()
    ).rstrip(b"=").decode()


def utcstamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def ledger_add(owner: str, kind: str, family: str, entry: dict,
                     handle: str | None = None) -> None:
    """One decision record. `handle` names the agent it was about, where
    there is one — see Store.ledger_add for why it is not part of `entry`."""
    await st(owner).ledger_add(kind, family, utcstamp(), entry, handle)


async def owner_notify(owner: str, payload: dict) -> None:
    await st(owner).notify(payload)


async def new_ticket(record: dict) -> str:
    """Mint a ticket and index it to the record's family, marked with the
    owner so it can be resolved on the way back in."""
    owner = record["owner"]
    ttl = PENDING_TTL if record.get("state") == "awaiting-owner" else TICKET_TTL
    raw = await st(owner).mint_ticket(record, ttl)
    return f"{_enc_owner(owner)}~{raw}"


async def close_negotiation(rec: dict | None) -> None:
    if rec:
        await st(rec["owner"]).close_negotiation(rec.get("family"))


# --- Basics -----------------------------------------------------------------


@app.on_event("startup")
async def open_store() -> None:
    await STORE.start()
    # An owner who has never been seen has no policy, and policy is what the
    # grant loop reads first. Seeding the ones this instance knows about at
    # startup keeps a cold database serviceable; an owner who appears later is
    # seeded when she first authenticates.
    await st(DEFAULT_OWNER).seed()


@app.on_event("shutdown")
async def close_store() -> None:
    await STORE.close()


@app.get("/health")
async def health() -> dict:
    """Liveness and readiness both.

    Deliberately independent of whether the registry pull has completed. The
    pull calls this AS's *public* hostname, which routes back here for a JWKS
    check — so gating readiness on it would leave this service with no ready
    endpoints, which fails the back-call, which fails the pull, which never
    lets readiness go green. See /health/registry for the honest answer to
    "has the pull finished", which is a question worth asking and a terrible
    readiness probe.
    """
    return {"status": "ok", "issuer": ISSUER}


@app.get("/health/registry")
async def health_registry() -> JSONResponse:
    """Has this replica's declarative pull landed yet?

    For `kubectl wait`, the smoke tests and a dashboard panel — never for a
    readiness probe (see /health).
    """
    ready = bool(RESOURCES)
    return JSONResponse(
        {"status": "ok" if ready else "pending", "resources": len(RESOURCES)},
        status_code=200 if ready else 503,
    )


@app.get("/jwks")
async def jwks() -> dict:
    jwk = json.loads(OKPAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    jwk.update({"kid": KID, "use": "sig"})
    return {"keys": [jwk]}


@app.get("/.well-known/uma4agents-configuration")
async def discovery() -> dict:
    return {
        "issuer": ISSUER,
        "token_endpoint": f"{ISSUER}/token",
        "permission_endpoint": f"{ISSUER}/perm",
        "introspection_endpoint": f"{ISSUER}/introspect",
        "jwks_uri": f"{ISSUER}/jwks",
        "terms_endpoint": f"{ISSUER}/terms",
        "grant_types_supported": ["urn:ietf:params:oauth:grant-type:uma-ticket"],
        "claim_token_formats_supported": [AGREEMENT_FORMAT],
    }


# --- Terms roster (MyTerms pattern: proffered terms are persistent documents) -

# Every version of every proffered terms document is kept dereferenceable at
# a stable URI for the life of the AS — the "persistent record of the
# policies the requesting party promises to adhere to" (2010), in MyTerms
# shape. They live in the store: a terms URI that resolved on one replica and
# 404'd on another would break exactly the property that makes a signed
# agreement checkable later.


def terms_uri(template_id: str) -> str:
    return f"{ISSUER}/terms/{template_id}"


def owner_of_template(template_id: str) -> str:
    """Template ids are namespaced by owner — `alice/advisor-tier1/v2` — so a
    terms document dereferenced by an agent who has no token still resolves to
    whose terms it is. That namespacing predates multi-owner; it just turned
    out to be the lookup."""
    head = (template_id or "").split("/", 1)[0]
    return head or DEFAULT_OWNER


async def publish_terms(owner: str, tier_id: str, tier: dict) -> str:
    """Archive the current version of a tier's terms as a served document.
    Idempotent per template_id (a version's content never changes)."""
    template_id = tier["terms"]["template_id"]
    if await st(owner).terms_doc(template_id) is None:
        # Whether a layer above the owner is in force over these resources,
        # stated in the document itself. An agent reads this before it has a
        # token and before it signs anything, which is the only moment at
        # which "these terms are not hers alone" is information it can act
        # on. Leaving it out would make the ceiling invisible to the one
        # party whose agreement is being asked for.
        record = await st(owner).organization()
        envelope = (record or {}).get("envelope") or {}
        governed = bool(envelope) and org.governs(tier, envelope)
        await st(owner).publish_terms({
            "template_id": template_id,
            "terms_uri": terms_uri(template_id),
            "proffered_by": ISSUER,
            "name": tier["name"],
            "tier": tier_id,
            **{k: v for k, v in tier["terms"].items() if k != "template_id"},
            **({"organization": {
                "name": envelope.get("name"),
                "id": envelope.get("org"),
                "issuer": envelope.get("issuer"),
                "charter_version": envelope.get("charter_version"),
                "requires": envelope.get("summary") or [],
            }} if governed else {}),
            "published_at": utcstamp(),
        })
        event("terms.published", template_id=template_id, tier=tier_id)
    return terms_uri(template_id)


async def ensure_owner(owner: str) -> None:
    """Seed an owner, and publish the terms documents her tiers name.

    Both halves, and the second is easy to miss: seeding creates the policy
    but a terms document is a *served* artifact, and the challenge tells an
    agent to go and fetch one. An owner who first appears after startup would
    otherwise have tiers whose `terms_uri` 404s — which fails at beat 2, in
    the agent, a long way from the cause.
    """
    await st(owner).seed()
    for tier_id, tier in (await st(owner).tiers()).items():
        await publish_terms(owner, tier_id, tier)


@app.on_event("startup")
async def publish_initial_terms() -> None:
    for owner in await STORE.owners() or [DEFAULT_OWNER]:
        await ensure_owner(owner)


@app.get("/terms")
async def terms_index(owner: str = None) -> dict:
    """One owner's proffered terms. `?owner=` on a multi-tenant instance;
    the served owner otherwise."""
    who = owner or DEFAULT_OWNER
    return {
        "owner": who,
        "proffered_by": ISSUER,
        "terms": await st(who).terms_docs(),
    }


def terms_as_html(doc: dict) -> str:
    """The plain-language representation IEEE 7012 (4.4.1) requires the terms
    themselves to carry — same URI as the machine-readable form.

    Every interpolation is escaped. Alice writes most of this herself through
    the owner API, so it is not obviously attacker-controlled — but a terms
    document is a public URL that agents dereference and quote, and a rendering
    that trusts its own stored values is one owner-API bug away from serving
    markup. Escaping here costs nothing and does not depend on that argument
    staying true."""
    e = html.escape
    enforced = doc.get("enforced") or {}
    prohibited = "".join(
        f"<li>{e(str(p))}"
        + (f" — <b>refused at the door</b> ({e(str(enforced[p]))})"
           if p in enforced else " — undertaken, not enforced")
        + "</li>"
        for p in doc.get("prohibited", []))
    scopes = e(", ".join(doc.get("scope", [])))
    hours = round(doc.get("expires_in", 0) / 3600, 1)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{e(str(doc['name']))} — {e(str(doc['template_id']))}</title>
<style>body{{background:#0b0e14;color:#e6e9f0;font-family:system-ui;max-width:640px;
margin:3rem auto;padding:0 1rem;line-height:1.6}}h1{{font-size:1.3rem}}
code{{background:#161b26;padding:2px 7px;border-radius:5px}}
.k{{color:#8a93a8}}li{{margin:.2rem 0}}</style></head><body>
<h1>{e(str(doc['name']))}</h1>
<p class="k">Terms <code>{e(str(doc['template_id']))}</code>, proffered by
<code>{e(str(doc['proffered_by']))}</code>, published {e(str(doc['published_at']))}.</p>
<p>The owner of these accounts offers access on the following terms. By
signing an agreement that names this document, you accept all of them.</p>
<ul>
<li><b>Purpose</b> — access is granted only for: {e(str(doc['purpose']))}.</li>
<li><b>What you may access</b> — {scopes}.</li>
<li><b>How long</b> — access expires {int(doc['expires_in'])} seconds
    (~{hours} hours) after grant.</li>
<li><b>Prohibited</b> — you agree you will not engage in:<ul>{prohibited}</ul></li>
<li><b>Anything not expressly permitted here is not permitted.</b></li>
</ul>
<p class="k">Machine-readable: this same URI as <code>application/json</code>,
or <code>?format=jsonld</code> for a JSON-LD/ODRL representation.</p>
</body></html>"""


def terms_as_jsonld(doc: dict) -> dict:
    """JSON-LD/ODRL representation (IEEE 7012 4.4.2 and Annex A principle (j):
    structured, IRI-linked terms; ODRL for permissions/prohibitions).
    Prohibition actions are fragment IRIs on the terms document itself, which
    dereferences to their definition."""
    uri = doc["terms_uri"]
    return {
        "@context": {
            "odrl": "http://www.w3.org/ns/odrl/2/",
            "dcterms": "http://purl.org/dc/terms/",
        },
        "@id": uri,
        "@type": "odrl:Offer",
        "odrl:uid": uri,
        "dcterms:title": doc["name"],
        "dcterms:identifier": doc["template_id"],
        "dcterms:publisher": doc["proffered_by"],
        "dcterms:issued": doc["published_at"],
        "dcterms:description": doc["purpose"],
        "odrl:permission": [
            {"odrl:action": f"{uri}#scope/{s}", "odrl:constraint": [
                {"odrl:leftOperand": "odrl:elapsedTime",
                 "odrl:operator": "odrl:lteq",
                 "odrl:rightOperand": {"@value": f"PT{doc['expires_in']}S",
                                        "@type": "xsd:duration"}}]}
            for s in doc.get("scope", [])
        ],
        "odrl:prohibition": [
            {"odrl:action": f"{uri}#prohibited/{p}"} for p in doc.get("prohibited", [])
        ],
    }


async def annotate_enforced(owner: str, doc: dict) -> dict:
    """Mark which prohibitions the enforcement point currently refuses.

    Computed on read and deliberately not stored. `publish_terms` is
    idempotent because an agreement names a version and must stay checkable
    against exactly the bytes that were proffered — so a document cannot gain
    a field later, and anything that can change without the terms changing has
    no business inside one. Whether reuse is refused depends on the tier's
    `per_operation` switch, which she can flip without rewriting a word.

    Only annotated while this version is the one in force. A superseded
    version would otherwise be labelled with today's posture, which is a
    different kind of wrong from saying nothing.
    """
    tiers = await st(owner).tiers()
    tier = tiers.get(doc.get("tier") or "")
    if not tier or tier["terms"]["template_id"] != doc["template_id"]:
        return doc
    return {**doc, "enforced": policy.enforced_prohibitions(tier)}


@app.get("/terms/{template_id:path}")
async def terms_document(template_id: str, request: Request, format: str = None):
    owner = owner_of_template(template_id)
    doc = await st(owner).terms_doc(template_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="unknown terms document")
    # The stored bytes are what was proffered and signed against. The
    # enforcement posture is annotated on top, never folded in.
    doc = await annotate_enforced(owner, doc)
    if format == "jsonld":
        return JSONResponse(terms_as_jsonld(doc), media_type="application/ld+json")
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept.split(",")[0]:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(terms_as_html(doc))
    return doc


def _bearer(request: Request) -> str:
    authz = request.headers.get("authorization", "")
    if not authz.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    return authz[7:]


async def issue_pat(owner: str, client_id: str) -> dict:
    """Mint a PAT: an OAuth access token for the Protection API, carrying
    the owner it acts about (FedAuthz's RO context) and the RS it was
    issued to."""
    exp = int(now()) + PAT_TTL
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": owner,
            "azp": client_id,
            "scope": "uma_protection",
            "jti": f"pat_{uuid.uuid4().hex[:12]}",
            "exp": exp,
        },
        SIGNING_KEY,
        algorithm="EdDSA",
        headers={"typ": "pat+jwt", "kid": KID},
    )
    await st(owner).touch_pat(client_id, utcstamp())
    event("pat.issued", client_id=client_id, expires_in=PAT_TTL)
    return {"access_token": token, "token_type": "Bearer",
            "expires_in": PAT_TTL, "scope": "uma_protection"}


async def require_pat(request: Request) -> str:
    """The Protection API takes the PAT this AS issued — verified, scoped,
    and revocable via the owner's resource-server registry.

    Returns the owner it was issued for. One resource server holds one PAT per
    owner it serves, so the token is what says whose resources this call is
    about; there is no other signal on a Protection API request."""
    try:
        claims = jwt.decode(_bearer(request), SIGNING_KEY.public_key(),
                            algorithms=["EdDSA"], issuer=ISSUER,
                            options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401,
                            detail=f"protection API requires a valid PAT: {exc}")
    if "uma_protection" not in claims.get("scope", "").split():
        raise HTTPException(status_code=403, detail="PAT lacks uma_protection scope")
    owner = claims.get("sub") or DEFAULT_OWNER
    if not serves(owner):
        raise HTTPException(status_code=403,
                            detail="this authorization server serves a different owner")
    rs = await st(owner).resource_server(claims.get("azp", ""))
    if rs is None or rs["status"] != "active":
        raise HTTPException(status_code=401,
                            detail="the owner has revoked this resource server")
    return owner


_OWNER_KEYS_CACHE: dict[str, tuple[float, list]] = {}


def owner_issuer_keys() -> list:
    cached = _OWNER_KEYS_CACHE.get(OWNER_ISSUER)
    if cached and cached[0] > now():
        return cached[1]
    import httpx

    with httpx.Client(verify=AGENT_ISSUER_CA or True, timeout=5.0) as client:
        meta = client.get(OWNER_METADATA_URL)
        meta.raise_for_status()
        jwks = client.get(meta.json()["jwks_uri"])
        jwks.raise_for_status()
    keys = jwks.json()["keys"]
    _OWNER_KEYS_CACHE[OWNER_ISSUER] = (now() + JWKS_CACHE_TTL, keys)
    return keys


_OWNER_KEY_CACHE: dict[str, object] = {}


def owner_device_key():
    """Her registered device key, in local-key mode.

    Read once and cached. A real deployment enrols this key — she proves
    possession of it on a device she already trusts — rather than finding it
    on disk; the lab writes it at first run so the stack has nothing to set up.
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    cached = _OWNER_KEY_CACHE.get(OWNER_KEY_PATH)
    if cached is not None:
        return cached
    try:
        with open(OWNER_KEY_PATH, "rb") as fh:
            key = load_pem_public_key(fh.read())
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=(f"UMA_AS_OWNER_AUTH=local-key but no owner key at "
                    f"{OWNER_KEY_PATH}: {exc}")) from exc
    _OWNER_KEY_CACHE[OWNER_KEY_PATH] = key
    return key


async def require_owner_signature(request: Request) -> str:
    """The owner signs her own request, with her own key.

    **A key names a holder, not an owner**, so the binding is configuration:
    `UMA_AS_OWNER_KEY` is registered *for* `UMA_AS_OWNER_KEY_OWNER`. Verifying
    the signature proves the holder; the registration says whose key it is.

    One key per instance is the lab's simplification, and the honest limit: a
    multi-tenant deployment serving a million people would hold these as
    per-owner records rather than one environment variable, keyed the same way
    everything else here is. The verification is unchanged either way — what
    changes is where the binding is read from.

    RFC 9421 over method, authority, path and authorization, verified with
    `lib/uma4a_http_sig.py` — the same module the enforcement point uses.
    There is no bearer token to steal, nothing to introspect, and no third
    party that has to be available: the authority holds one public key.

    **A request with a body must also cover an RFC 9530 Content-Digest.** The
    four base components say who is asking and what they are asking of; they
    say nothing about the bytes. That is adequate for a GET and unsafe for
    `POST /owner/pending/{family}/decision`, whose whole meaning is a word in
    its body: without the digest an intermediary can leave her signature
    untouched and turn an approval into a refusal. The family is in the path
    and so cannot be retargeted — but the answer could be inverted, which is
    worse, because it is silent and it is hers.

    `authorization` is part of the signature base whether or not it carries a
    value, so an owner request that has no bearer token signs the empty
    string.
    """
    from uma4a_http_sig import VerifyError
    from uma4a_http_sig import verify as verify_sig

    sig_input = request.headers.get("signature-input")
    sig = request.headers.get("signature")
    if not sig_input or not sig:
        raise HTTPException(
            status_code=401,
            detail="owner API requires an RFC 9421 signature from the owner's key")

    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    # Read once and cache on the request: FastAPI's body() is memoised, so the
    # route handler still gets it after this.
    body = await request.body()
    try:
        verify_sig(
            method=request.method,
            authority=OWNER_EXPECTED_AUTHORITY,
            path=path,
            authorization=request.headers.get("authorization", ""),
            signature_input=sig_input,
            signature=sig,
            public_key=owner_device_key(),
            body=body if body else None,
            require_digest=bool(body),
            digest_header=request.headers.get("content-digest"),
        )
    except VerifyError as exc:
        raise HTTPException(
            status_code=401, detail=f"owner signature did not verify: {exc}") from exc

    # Named, never inferred. Treating a valid signature as "whoever the
    # request seems to be about" would let one key holder act as somebody
    # else's authority, which is the thing this service exists to prevent.
    return OWNER_KEY_OWNER


async def require_owner(request: Request) -> str:
    """Whoever is calling the owner API has to be an owner, and gets their own.

    Returns the owner the credential proved, which is the only thing every
    handler below then uses to reach the store. There is no ambient owner: a
    handler that forgets to ask cannot read anything.

    Any configured credential that verifies is enough — she is one person
    however she reached this. Every owner endpoint calls this, so none of them
    needs to know which credentials the deployment accepts.

    A 401 is returned only when *no* configured mode verifies, and it carries
    the last reason rather than a list, so a caller presenting one credential
    is told why that one failed instead of why the others did.
    """
    unknown = [m for m in OWNER_AUTH if m not in VERIFY_OWNER]
    if unknown or not OWNER_AUTH:
        raise HTTPException(
            status_code=500,
            detail=(f"UMA_AS_OWNER_AUTH must be a comma-separated list of "
                    f"{'|'.join(sorted(VERIFY_OWNER))}; got {unknown or 'nothing'}"))

    # Which failure to report when several modes are configured and all of
    # them fail. "The last one" is the obvious choice and the wrong one: a 403
    # from a credential that *did* authenticate ("this server serves a
    # different owner") is the useful answer, and it was being overwritten by
    # a later mode's 401 for a credential that was never presented. Prefer the
    # most advanced failure.
    last: HTTPException | None = None
    best: HTTPException | None = None
    for mode in OWNER_AUTH:
        try:
            result = VERIFY_OWNER[mode](request)
            if hasattr(result, "__await__"):
                owner = await result
            else:
                owner = result
            owner = owner or DEFAULT_OWNER
            if not serves(owner):
                raise HTTPException(
                    status_code=403,
                    detail="this authorization server serves a different owner")
            # An owner seen for the first time gets her starting policy here,
            # which is also the moment a multi-tenant deployment learns she
            # exists.
            await ensure_owner(owner)
            return owner
        except HTTPException as exc:
            last = exc
            if best is None or exc.status_code > best.status_code:
                best = exc
    raise best or last or HTTPException(status_code=401,
                                        detail="owner authentication failed")


def require_owner_oidc(request: Request) -> str:
    """One of the credentials: Alice's own OIDC access token, validated against
    her realm's published keys. The portal proxies it; the simulated Alice
    obtains one by actually logging in (direct-access grant)."""
    from jwt.algorithms import RSAAlgorithm

    token = _bearer(request)
    try:
        header = jwt.get_unverified_header(token)
        claims = None
        last_error: Exception | None = None
        for jwk_dict in owner_issuer_keys():
            if jwk_dict.get("use") == "enc":
                continue
            if header.get("kid") and jwk_dict.get("kid") != header["kid"]:
                continue
            try:
                claims = jwt.decode(
                    token, RSAAlgorithm.from_jwk(json.dumps(jwk_dict)),
                    algorithms=["RS256"], issuer=OWNER_ISSUER,
                    options={"verify_aud": False})
                break
            except jwt.InvalidTokenError as exc:
                last_error = exc
        if claims is None:
            raise last_error or ValueError("no matching realm key")
    except Exception as exc:
        raise HTTPException(status_code=401,
                            detail=f"owner API requires the owner's OIDC token: {exc}")
    if claims.get("azp") not in OWNER_AUDIENCES:
        raise HTTPException(status_code=403,
                            detail="token was not issued to an owner-surface client")
    # The authenticated username *is* the owner. Whether this instance serves
    # her is decided once, in require_owner, rather than here.
    owner = claims.get("preferred_username")
    if not owner:
        raise HTTPException(status_code=403,
                            detail="owner token carries no preferred_username")
    return owner



# Filled after both verifiers exist. A deployment names the credentials it
# accepts; this maps each name to the code that checks it.
VERIFY_OWNER = {
    "oidc": require_owner_oidc,
    "local-key": require_owner_signature,
}


# --- Declarative registration (pull mode) -------------------------------------


def well_known_prm_url(resource_uri: str) -> str:
    from urllib.parse import urlparse

    u = urlparse(resource_uri)
    return (f"{u.scheme}://{u.netloc}"
            f"/.well-known/oauth-protected-resource{u.path.rstrip('/')}")


def pull_registrations(client_id: str, rs: dict) -> int:
    """Read the RS's published metadata and materialize the registry.

    Takes the resource-server record rather than looking it up: this runs on
    a worker thread (see pull_at_startup) and so cannot reach the store.

    1. Fetch the public RFC 9728 document (TLS-anchored) and verify its
       signed_metadata against the resource's jwks_uri — the pulled copy is
       attributable, not just transport-secure.
    2. Query the protected owner-resources endpoint it advertises, signing
       the request with this AS's key (RFC 9421) — "protected webfinger":
       the RS serves the owner-bound instances only to her AS.
    """
    import httpx

    from uma4a_http_sig import sign as http_sign

    resource_uri = rs["resource_uri"]
    with httpx.Client(verify=AGENT_ISSUER_CA or True, timeout=10.0) as client:
        prm = client.get(well_known_prm_url(resource_uri))
        prm.raise_for_status()
        doc = prm.json()
        if doc.get("resource") != resource_uri:
            raise ValueError(f"metadata is for {doc.get('resource')!r}")
        if ISSUER not in doc.get("authorization_servers", []):
            raise ValueError("the RS's metadata does not name this AS")

        jwks = client.get(doc["jwks_uri"])
        jwks.raise_for_status()
        signed = doc.get("signed_metadata")
        if not signed:
            raise ValueError("published metadata is not signed")
        verified = None
        for jwk_dict in jwks.json()["keys"]:
            try:
                verified = jwt.decode(signed, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                      algorithms=["EdDSA"],
                                      options={"verify_aud": False})
                break
            except jwt.InvalidTokenError:
                continue
        if verified is None or verified.get("iss") != resource_uri:
            raise ValueError("signed_metadata did not verify against the "
                             "resource's published keys")

        endpoint = verified.get("owner_resources_endpoint")
        if not endpoint:
            raise ValueError("no owner_resources_endpoint in signed metadata")
        from urllib.parse import urlparse

        u = urlparse(endpoint)
        headers = http_sign(method="GET", authority=u.netloc, path=u.path,
                            authorization="", key=SIGNING_KEY, keyid=KID)
        listing = client.get(endpoint, headers=headers)
        listing.raise_for_status()
        body = listing.json()

    # The listing replaces what this resource server publishes for this
    # owner rather than merging into it.
    #
    # Merging was wrong in a way that only showed up once resources could be
    # *withdrawn*. A resource server that stops publishing something — an
    # organization that stopped sharing its book with this member, an account
    # that was closed — had no way to say so: the id stayed in this registry
    # for the life of the process, and a stale tier over it went on issuing
    # tickets for a resource nobody was serving. Declarative registration
    # means the published document is the truth, and that has to include the
    # absences.
    seen, count = set(), 0
    for res in body.get("resources", []):
        RESOURCES[res["_id"]] = {
            "resource_scopes": res["resource_scopes"],
            "name": res.get("name"),
            "type": res.get("type"),
            "icon_uri": None,
            "description": None,
            "registered_via": "pull",
            "owner": body.get("owner"),
            "source": client_id,
        }
        seen.add(res["_id"])
        count += 1
    withdrawn = [rid for rid, d in RESOURCES.items()
                 if d.get("source") == client_id
                 and d.get("owner") == body.get("owner") and rid not in seen]
    for rid in withdrawn:
        RESOURCES.pop(rid, None)
    event("resources.pulled", client_id=client_id, owner=body.get("owner"),
          count=count, withdrawn=withdrawn or None, endpoint=endpoint)
    return count


@app.on_event("startup")
async def pull_at_startup() -> None:
    async def attempt_loop():
        for _ in range(60):
            owners = await STORE.owners() or [DEFAULT_OWNER]
            pairs = [(o, cid, rs) for o in owners
                     for cid, rs in (await st(o).resource_servers()).items()]
            for owner, client_id, rs in pairs:
                try:
                    # Off the event loop: the RS authenticates this AS's
                    # signed query by fetching *our* JWKS, so the pull and
                    # the verification form a call cycle — a blocking pull
                    # deadlocks a single-threaded AS. (Finding: pull-model
                    # verification must tolerate a live back-call, or keys
                    # must be cached ahead of need.)
                    #
                    # The same cycle is why /health must not report this
                    # loop's progress: under an orchestrator that gates
                    # traffic on readiness, the back-call would have nowhere
                    # to land and the loop could never finish.
                    await asyncio.to_thread(pull_registrations, client_id, rs)
                    return
                except Exception as exc:
                    event("resources.pull_retry", client_id=client_id,
                          error=str(exc)[:200])
            await asyncio.sleep(2)
        event("resources.pull_failed", note="lazy pull on first /perm remains")

    asyncio.create_task(attempt_loop())


# --- Protection API (gateway-side, FedAuthz shape) ---------------------------


@app.post("/perm")
async def register_permission(request: Request) -> JSONResponse:
    owner = await require_pat(request)
    body = await request.json()
    rid = body.get("resource_id")
    # FedAuthz §4.1: the AS only issues tickets against its own registry.
    registered = RESOURCES.get(rid)
    if registered is None:
        # An unknown id means our pulled copy may be stale, so re-read what
        # the RS publishes. Staleness is the price of declarative
        # registration, and repairing it is this side's job — the mirror of
        # the RS-side re-push that classic RReg required.
        # (to_thread: see pull_at_startup — the pull triggers a JWKS
        # back-call from the RS and must not block this event loop.)
        for client_id, rs in (await st(owner).resource_servers()).items():
            try:
                await asyncio.to_thread(pull_registrations, client_id, rs)
            except Exception as exc:
                event("resources.pull_retry", client_id=client_id,
                      error=str(exc)[:200])
        registered = RESOURCES.get(rid)
    if registered is None:
        event("permission.rejected", resource_id=rid, reason="invalid_resource_id")
        return JSONResponse(
            {"error": "invalid_resource_id",
             "error_description": "resource is not registered at this AS"},
            status_code=400,
        )
    scopes = body.get("resource_scopes") or []
    if not scopes or not set(scopes).issubset(set(registered["resource_scopes"])):
        event("permission.rejected", resource_id=rid, reason="invalid_scope",
              requested=scopes)
        return JSONResponse(
            {"error": "invalid_scope",
             "error_description": "requested scopes exceed the registered resource"},
            status_code=400,
        )
    family = f"fam_{secrets.token_urlsafe(8)}"
    ticket = await new_ticket(
        {
            "owner": owner,
            "family": family,
            "state": "issued",
            "resource_id": rid,
            "resource_scopes": scopes,
        }
    )
    event("permission.registered", corr=family, resource_id=rid, scopes=scopes)
    return JSONResponse({"ticket": ticket}, status_code=201)


async def _decode_rpt(token: str) -> tuple[dict | None, dict | None, str]:
    """Decode and look up an RPT. Returns (claims, record, error_code)."""
    try:
        claims = jwt.decode(
            token,
            SIGNING_KEY.public_key(),
            algorithms=["EdDSA"],
            issuer=ISSUER,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        return None, None, "expired"
    except jwt.InvalidTokenError:
        return None, None, "invalid_signature"
    owner = claims.get("owner") or DEFAULT_OWNER
    rec = await st(owner).rpt(claims.get("jti", ""))
    if rec is None:
        return claims, None, "unknown_token"
    if (conn := await st(owner).connection(rec.get("handle") or "")) is not None:
        if conn["status"] != "active":
            return claims, rec, "connection_revoked"
    if claims.get("single_use") and rec["consumed"]:
        return claims, rec, "already_consumed"
    return claims, rec, ""


@app.post("/introspect")
async def introspect(request: Request, token: str = Form(...), consume: str = Form(None)) -> dict:
    await require_pat(request)
    claims, rec, err = await _decode_rpt(token)
    if err:
        # RFC 7662 permits additional members. Without a reason the PEP cannot
        # tell "come back after re-negotiating" from "the owner revoked you and
        # re-negotiating is pointless" — and sends revoked agents round a loop.
        event("rpt.introspected", corr=(rec or {}).get("family"), result=err)
        return {"active": False, "error": err}

    owner = claims.get("owner") or DEFAULT_OWNER
    # A withdrawal that left live grants working would be a withdrawal in
    # name only — the charter's ceiling caps them at an hour, and an hour is
    # a long time to be reading a book you have been shut out of. Checked on
    # every introspection, which the enforcement point performs on every
    # call, so it takes effect at once and needs no token machinery of its
    # own.
    if rec.get("handle") and await org_blocks_agent(owner, rec["handle"]):
        org_env, _ = await org_scope(owner)
        if any(org.reaches(p.get("resource_id") or "", org_env)
               for p in claims.get("permissions") or []):
            event("rpt.introspected", corr=rec["family"],
                  result="organization_revoked")
            return {"active": False, "error": "organization_revoked"}
    if rec.get("handle"):
        await st(owner).touch_connection(rec["handle"], utcstamp())
    # Consumption is no longer done here by default: the PEP has not yet
    # verified proof-of-possession at this point, so burning the token now
    # lets an unsigned replay destroy a grant the owner just approved. The
    # PEP calls /consume once every check has passed. The parameter is kept
    # for the single-shot case where a caller has already verified.
    if claims.get("single_use") and consume == "true":
        if await st(owner).consume_rpt(claims.get("jti", "")) is None:
            event("rpt.introspected", corr=rec["family"], result="already_consumed")
            return {"active": False, "error": "already_consumed"}
        event("rpt.consumed", corr=rec["family"], jti=claims.get("jti", ""))

    event("rpt.introspected", corr=rec["family"], result="active")
    return {
        "active": True,
        "family": rec["family"],
        "iss": claims["iss"],
        "sub": claims.get("sub"),
        "exp": claims["exp"],
        "permissions": claims["permissions"],
        "cnf": claims.get("cnf"),
        "contract": claims.get("contract"),
        "single_use": claims.get("single_use", False),
        "operation": claims.get("operation"),
    }


@app.post("/consume")
async def consume_rpt(request: Request, token: str = Form(...)) -> dict:
    """Burn a single-use RPT — the last step of enforcement, not the first.

    Split out of introspection so the PEP can verify proof-of-possession and
    the operation binding *before* anything is spent. The burn is the atomic
    step: whoever loses the race is told so, and must deny.

    That word "atomic" used to be aspirational. The decode above is a read
    and the burn below is a write, and this was safe only because one event
    loop never yielded between them — a property of the deployment, not of
    the design. It is now a property of the store: a single statement that
    both decides and writes, and reports which caller won. UMA 2.0 says an
    RPT may be single-use; it never says the burn must be indivisible,
    because in 2018 an authorization server was one process.
    """
    pat_owner = await require_pat(request)
    claims, rec, err = await _decode_rpt(token)
    if err:
        return {"consumed": False, "error": err}
    if not claims.get("single_use"):
        return {"consumed": False, "error": "not_single_use"}
    owner = claims.get("owner") or DEFAULT_OWNER
    if owner != pat_owner:
        # The enforcement point holds one PAT per owner it serves. Presenting
        # a grant of Alice's under Carol's PAT is not a mix-up to tolerate.
        event("rpt.consume_refused", corr=None, reason="owner_mismatch")
        return {"consumed": False, "error": "owner_mismatch"}
    family = await st(owner).consume_rpt(claims.get("jti", ""))
    if family is None:
        return {"consumed": False, "error": "already_consumed"}
    event("rpt.consumed", corr=family, jti=claims.get("jti", ""))
    return {"consumed": True, "family": family}


@app.post("/audit/access")
async def audit_access(request: Request) -> dict:
    """The PEP reports allowed calls so the ledger's 'touched' column is
    grounded in enforcement, not client claims."""
    owner = await require_pat(request)
    body = await request.json()
    family = body.get("family", "?")
    # The enforcement point reports what it allowed; the authority decides
    # whose it was, and against which of her tiers. It is never told the handle — it enforces for a policy it
    # cannot read, and the connection is the owner's record, not its.
    grant = await st(owner).grant_for_family(family)
    await ledger_add(owner, "touched", family, {
        "tool": body.get("tool"),
        "summary": body.get("summary"),
        "tier": (grant or {}).get("tier"),
    }, handle=(grant or {}).get("handle"))
    event("access.allowed", corr=body.get("family"), tool=body.get("tool"))
    return {"recorded": True}


# --- The organization above her, if she has joined one -----------------------
#
# Everything in this section is inert for an owner who is nobody's member,
# which is the default and the case the rest of this service was written
# for. What it adds is the arrangement the person-scale demo cannot express:
# a firm holds the account, Alice administers its sharing, and the firm's
# policy is above hers rather than beside it.
#
# Three places the organization is felt, and they are deliberately different
# mechanisms:
#
#   1. **Her terms are clamped** to the ceiling, on enrolment and whenever
#      the charter changes, so what the organization requires is written into
#      the document agents dereference and sign rather than applied
#      invisibly at the door.
#   2. **Its decision is asked for** on each request over a resource it
#      claims, and folded into hers. Either layer may refuse; neither can
#      widen the other.
#   3. **Break-glass arrives as a notice.** Those grants never pass through
#      here — the organization signs them itself — so what this service does
#      with one is put it in her ledger and on her screen the moment it is
#      opened, before any data has moved.

_ORG: dict[str, org.OrgClient] = {}
_ORG_JWKS: dict[str, tuple[float, list]] = {}
# When this process last re-read what the resource server publishes for an
# owner, so her own listing can repair a stale replica without turning every
# page load into a pull. See `owner_resources`.
_LAST_PULL: dict[str, float] = {}
RESOURCE_REFRESH_S = float(os.environ.get("UMA_AS_RESOURCE_REFRESH_S", "15"))


async def org_record(owner: str) -> dict | None:
    return await st(owner).organization()


async def org_client(owner: str) -> org.OrgClient | None:
    """This owner's organization, envelope refreshed if it is due.

    Returns None when she is nobody's member — including when she has just
    stopped being one, which this is where the server finds out about if the
    organization's notice never arrived.
    """
    client = _ORG.get(owner)
    if client is None:
        record = await org_record(owner)
        if record is None:
            return None
        if not record.get("issuer") or not record.get("token"):
            # A record without the two things that make it a membership. It
            # should not be possible to store one — see the refresh below,
            # which used to be able to — and an enrolment that cannot be used
            # is worse than none: every request over the organization's
            # resources would fail on a KeyError inside the grant loop.
            event("org.record_unusable", owner=owner, keys=sorted(record))
            await st(owner).clear_organization()
            return None
        client = _ORG[owner] = org.OrgClient(
            record["issuer"], record["token"], record.get("envelope") or {})
    if not client.stale():
        return client

    envelope, error = await client.refresh()
    if error == "membership_ended":
        # The organization refused this membership token. Before concluding
        # that she is no longer a member, check that the token this process
        # was holding is still the one on record.
        #
        # It is not always. This client is per process, the record is shared,
        # and a rejoin mints a new token: a replica that missed the rejoin
        # refreshes with the old one, is told it is not current — which is
        # true of the token and false of the membership — and would end an
        # enrolment the other replicas are happily using. Check-and-act
        # against the record, not against the cache.
        record = await org_record(owner)
        if record and record.get("token") != client.token:
            event("org.client_stale", owner=owner)
            _ORG.pop(owner, None)
            return await org_client(owner)
        await end_membership(owner, "your organization ended this membership")
        return None
    if error:
        event("org.unreachable", owner=owner, error=error,
              usable=not client.unusable())
        return client
    record = await org_record(owner)
    if record is None:
        # She stopped being a member while this refresh was in flight —
        # another replica cleared it, or she left from her portal. Writing
        # the envelope back now would recreate the record with nothing in it
        # but a ceiling, which is not a membership and cannot be used.
        _ORG.pop(owner, None)
        return None
    known = (record.get("envelope") or {}).get("charter_version")
    record["envelope"] = envelope
    await st(owner).set_organization(record)
    if envelope.get("charter_version") != known:
        # The organization edited its charter. Her terms are re-clamped to
        # the new ceiling here rather than at the next request, because the
        # terms document is what an agent reads *before* it asks, and a
        # document that is briefly out of date is one an agent can sign.
        event("org.charter_changed", owner=owner, was=known,
              now=envelope.get("charter_version"))
        await clamp_to_envelope(owner, envelope, force=True)
        await resync_shared(owner, envelope)
    return client


async def clamp_to_envelope(owner: str, envelope: dict,
                            force: bool = False) -> list[dict]:
    """Narrow every governed tier to the ceiling, and say what moved.

    `force` republishes governed tiers whose terms already fit. That is not
    busywork: a tier under an organization discloses the organization in its
    terms document, so enrolment and a charter change both alter what the
    document says even when no field of hers had to move. The version bump is
    what makes that disclosure reach an agent instead of sitting in a
    document nobody re-reads.
    """
    changed: list[dict] = []
    for tier_id, tier in (await st(owner).tiers()).items():
        patch, changes = org.patch_for(tier, envelope)
        if patch is None:
            if not (force and org.governs(tier, envelope)):
                continue
            patch = {}
        updated = await st(owner).update_tier(tier_id, patch)
        await publish_terms(owner, tier_id, updated)
        if changes:
            event("org.clamped", owner=owner, tier=tier_id,
                  fields=[c["field"] for c in changes])
            await ledger_add(owner, "org_clamped", "-", {
                "tier": tier_id,
                "organization": envelope.get("name"),
                "charter_version": envelope.get("charter_version"),
                "changes": [c["text"] for c in changes],
            })
        changed += [{"tier": tier_id, **c} for c in changes]

    client = _ORG.get(owner)
    if client is not None:
        await client.report(org.compliance(
            await st(owner).tiers(), envelope, list(RESOURCES),
            clamped_fields=[c["field"] for c in changed]))
    return changed


async def pull_registrations_now(owner: str) -> None:
    """Re-read what this owner's resource servers publish.

    Extracted because three things now need it and they need it for the same
    reason: `RESOURCES` is a per-process cache of somebody else's listing,
    and the events that change that listing happen elsewhere. Her portal
    re-reads it on a clock; `/perm` re-reads it on a miss; and joining a
    jointly held account re-reads it because the resources the mandate names
    have to exist here before she can write a word of terms over them — and
    a holder with no terms is a holder who has consented to nothing.
    """
    _LAST_PULL[owner] = time.time()
    for client_id, rs in (await st(owner).resource_servers()).items():
        try:
            await asyncio.to_thread(pull_registrations, client_id, rs)
        except Exception as exc:                                # noqa: BLE001
            event("resources.pull_retry", client_id=client_id,
                  error=str(exc)[:200])


async def resync_shared(owner: str, envelope: dict | None,
                        claims: list | None = None) -> None:
    """Re-read what this owner's resource server publishes, and drop what the
    organization no longer shares with her.

    Membership is what makes a shared resource exist at her authority. The
    gateway publishes it to her only while she holds a role that grants it,
    so a pull is enough to *add* one — but a pull merges rather than
    replaces, so something withdrawn has to be removed here.

    Both directions matter and only one of them is obvious. Adding is the
    reason she joined. Removing is the reason leaving is safe: her tier over
    the firm's book survives, and governs nothing, so an agent presenting an
    old grant gets an unregistered resource rather than her terms.
    """
    for client_id, rs in (await st(owner).resource_servers()).items():
        try:
            await asyncio.to_thread(pull_registrations, client_id, rs)
        except Exception as exc:                                # noqa: BLE001
            event("resources.pull_retry", client_id=client_id,
                  error=str(exc)[:200])
    claims = claims if claims is not None else (envelope or {}).get("claims") or []
    grants = (envelope or {}).get("grants") or []
    excluded = await jointly_held(owner)
    stale = [r for r in list(RESOURCES)
             if r not in excluded and org.claims_match(r, claims)
             and not org.claims_match(r, grants)]
    if not stale:
        return
    if SERVED_OWNER is None:
        # This process holds more than one owner, and `RESOURCES` is its
        # registry rather than hers: an organization's resource has the same
        # id for every member it is shared with, so removing it here on one
        # member's account would remove it from the others too. Left in place
        # and said out loud. Nothing is granted by its presence — her policy
        # is what grants, the organization's decision point is asked on every
        # request over its resources, and the enforcement point refuses a
        # member it is no longer sharing with.
        event("resources.unshared_skipped", owner=owner, resources=stale,
              why="this process serves more than one owner")
        return
    for rid in stale:
        RESOURCES.pop(rid, None)
        event("resources.unshared", owner=owner, resource_id=rid)


async def end_membership(owner: str, why: str) -> None:
    """Stop being governed, from either side's initiative.

    Her tiers are left exactly as they are. They were narrowed while she was
    a member and they stay narrowed — an envelope is a ceiling, and taking a
    ceiling away does not raise what is underneath it. Anything she wants
    back she can widen herself, deliberately, one tier at a time, which is
    the only way access should ever grow.
    """
    record = await org_record(owner)
    claims = ((record or {}).get("envelope") or {}).get("claims") or []
    _ORG.pop(owner, None)
    if not await st(owner).clear_organization():
        return
    # Her rights over the organization's resources end with the membership
    # that granted them. Her *terms* are untouched — see the note below —
    # but the resources those terms were written over stop being hers to
    # administer, which is the honest meaning of shared ownership ending.
    await resync_shared(owner, None, claims)
    event("org.membership_ended", owner=owner, why=why)
    await ledger_add(owner, "org_left", "-", {"why": why})
    await owner_notify(owner, {"type": "organization", "state": "ended",
                               "why": why})


async def jointly_held(owner: str) -> set[str]:
    """Every resource this owner holds jointly with somebody else."""
    out: set[str] = set()
    for record in (await st(owner).mandates()).values():
        out |= set((record.get("mandate") or {}).get("resources") or [])
    return out


async def org_envelope(owner: str) -> dict | None:
    """The organization's ceiling, with what it may not reach subtracted.

    The subtraction is done here rather than at each of the six surfaces that
    read a ceiling, because it is a property of *this owner's* situation and
    not of the charter: an organization's claims are the same for every
    member, and what any one of them holds jointly is not.
    """
    client = await org_client(owner)
    if client is None:
        return None
    return {**client.envelope, "excluded": sorted(await jointly_held(owner))}


async def organization_blocks(owner: str, resource_id: str) -> str | None:
    """Why a request over this resource cannot proceed, or None.

    The one case: the organization's ceiling could not be re-read for longer
    than this server is willing to act on a stale copy of it. A ceiling
    nobody can read is not a ceiling, and the direction to fail in is
    obvious — the resource belongs to the organization.
    """
    client = await org_client(owner)
    if client is None:
        return None
    if not org.reaches(resource_id, await org_envelope(owner) or {}):
        return None
    if client.unusable():
        return (f"{client.envelope.get('name')}'s policy could not be read, "
                f"and access to its resources does not proceed without it")
    # Claimed by the organization, but not shared with *her*. Refused before
    # her terms are ever dictated, because there is nothing for her to offer:
    # these are somebody else's resources and her role does not include them.
    #
    # The distinction between this and an ordinary refusal is worth keeping.
    # "Your organization has not shared this with you" is a fact about the
    # relationship the member can act on — by asking an administrator — and
    # it is not a judgement about the agent at all.
    if not org.claims_match(resource_id, client.envelope.get("grants") or []):
        role = client.envelope.get("role_name") or client.envelope.get("role")
        return (f"{client.envelope.get('name')} has not shared this resource "
                f"with you" + (f" — your role here is {role}" if role else
                               ", and you hold no role there"))
    return None


async def organization_verdict(rec: dict, tier: dict, facts: dict) -> dict:
    """The organization's answer about this request, or {} if it has none.

    Its `allow` means "no objection", never "grant" — her tiers are what
    permit, and nothing returned here is capable of making a request easier
    than her own policy already makes it. The only two things this can do are
    put the request in front of her, and stop it.
    """
    client = await org_client(rec["owner"])
    if client is None:
        return {}
    # Whether this is the organization's business at all, decided here from
    # the ceiling this server already holds — before any call is made.
    #
    # Asking first and reading `governed` out of the answer was wrong in the
    # one case that matters: when the organization cannot be reached, the
    # failure path returns a refusal, and a refusal it has no standing to
    # give. Her own brokerage account stopped working because somebody else's
    # policy service was restarting. An organization's outage must be
    # survivable by everything it does not govern.
    if not org.reaches(rec["resource_id"], await org_envelope(rec["owner"]) or {}):
        return {}
    contract = rec.get("contract") or {}
    verdict = await client.decide({
        "resource_id": rec["resource_id"],
        "scopes": list(rec.get("resource_scopes") or []),
        "tier": rec.get("tier"),
        "expires_in": contract.get("expires_in", 0),
        "purpose": contract.get("purpose"),
        "reason": contract.get("reason"),
        "mission": contract.get("mission"),
        "operation": contract.get("operation"),
        "assurance": facts["assurance"],
        "standing": facts["standing"],
    })
    if not verdict.get("governed"):
        return {}
    return {**verdict, "organization": client.envelope.get("name"),
            "org": client.envelope.get("org")}


# --- Notices from the organization -------------------------------------------


def issuer_keys(issuer: str, fresh: bool = False) -> list:
    """The signing keys a party publishes, cached.

    Used for any peer this server has to verify rather than trust: the
    organization above an owner, and the tally that counts verdicts over a
    resource she holds jointly. One cache, because the question is the same
    one — what does this issuer sign with — and two would be two TTLs to
    reason about.
    """
    cached = _ORG_JWKS.get(issuer)
    if cached and cached[0] > now() and not fresh:
        return cached[1]
    import httpx

    with httpx.Client(verify=org.CA_BUNDLE or True, timeout=5.0) as client:
        jwks = client.get(f"{issuer.rstrip('/')}/jwks")
        jwks.raise_for_status()
    keys = jwks.json()["keys"]
    _ORG_JWKS[issuer] = (now() + 300, keys)
    return keys


@app.post("/org/notice")
async def org_notice(request: Request) -> dict:
    """Something the organization wants this owner told.

    Verified against the organization's published keys rather than a shared
    secret or a network position, because the interesting forgery is an agent
    posting a break-glass notice to make an owner believe her firm took data
    it never touched — or, worse, to train her to expect notices that mean
    nothing. Only the organization she enrolled with can sign one.
    """
    body = await request.json()
    try:
        unverified = jwt.decode(body.get("notice") or "",
                                options={"verify_signature": False})
    except jwt.InvalidTokenError:
        # Unauthenticated by construction — anyone can post here and the
        # signature is what settles it — so malformed input has to be a
        # refusal rather than a traceback.
        raise HTTPException(status_code=400, detail="that is not a notice")
    owner = unverified.get("sub") or ""
    if not serves(owner):
        raise HTTPException(status_code=404, detail="not an owner here")
    record = await org_record(owner)
    if record is None:
        raise HTTPException(status_code=403, detail="not enrolled")
    issuer = record["issuer"]
    claims = None
    for jwk_dict in issuer_keys(issuer):
        try:
            claims = jwt.decode(body["notice"],
                                OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                algorithms=["EdDSA"], issuer=issuer,
                                options={"verify_aud": False})
            break
        except jwt.InvalidTokenError:
            continue
    if claims is None or claims.get("sub") != owner:
        raise HTTPException(status_code=401,
                            detail="that notice is not signed by this owner's "
                                   "organization")

    kind = claims.get("kind")
    event("org.notice", owner=owner, kind=kind)
    if kind == "membership_ended":
        await end_membership(owner, "your organization ended this membership")
        return {"received": kind}
    if kind == "role_changed":
        # What she may reach has changed. Re-read the envelope — which now
        # carries a different set of grants — and let the resources follow.
        client = _ORG.get(owner)
        if client is not None:
            client.fetched = 0.0
        envelope = await org_envelope(owner)
        await resync_shared(owner, envelope)
        await ledger_add(owner, "org_role", "-", {
            "organization": (record.get("envelope") or {}).get("name"),
            "role": claims.get("role"), "by": claims.get("by")})
        await owner_notify(owner, {"type": "organization", "state": "role",
                                   "role": claims.get("role"),
                                   "by": claims.get("by")})
        return {"received": kind, "role": claims.get("role")}
    if kind == "charter_changed":
        client = _ORG.get(owner)
        if client is not None:
            client.fetched = 0.0           # force the next read to be fresh
        envelope = await org_envelope(owner)
        return {"received": kind,
                "charter_version": (envelope or {}).get("charter_version")}

    # The break-glass family. All three are records first and notifications
    # second: a toast she was not at her desk for is not a record, and the
    # ledger is what she will read afterwards.
    if kind in ("break_glass_opened", "break_glass", "break_glass_used"):
        await ledger_add(owner, "break_glass", claims.get("jti") or "-", {
            "stage": kind,
            "organization": (record.get("envelope") or {}).get("name"),
            "resource_id": claims.get("resource_id"),
            "resources": claims.get("resources"),
            "reason": claims.get("reason"),
            "authorised_by": claims.get("authorised_by") or claims.get("by"),
            "tool": claims.get("tool"),
            "summary": claims.get("summary"),
            "expires_in": claims.get("expires_in") or claims.get("window_s"),
            "charter_version": claims.get("charter_version"),
        })
        await owner_notify(owner, {"type": "break_glass", "stage": kind,
                                   "resource_id": claims.get("resource_id"),
                                   "reason": claims.get("reason"),
                                   "by": claims.get("authorised_by")
                                         or claims.get("by")})
        return {"received": kind}
    return {"received": kind or "unknown"}


# --- Delegated administration ------------------------------------------------
#
# The other half of "the organization owns the data", and the half the
# ceiling cannot express. A firm whose accounts these are does not only want
# a bound on what its people may permit; it wants to be able to answer for
# what is connected to them. PP2PI calls this quadrant co-administration —
# two administrators over one subject's resources — and it has always been
# the arrangement that had a name and no mechanism.
#
# What an administrator can do here is exactly what she can do, with one
# asymmetry that runs through everything else in this profile:
#
#   * **restrictions are unrestricted.** Revoke an agent, block an operator,
#     deny a pending request — any of it, any time. The worst outcome of an
#     administrator being wrong about a restriction is friction;
#   * **permissions are bounded by the charter.** An approval is only
#     available over a resource the organization actually claims. An
#     administrator approving an agent's access to a member's *own* accounts
#     would not be co-administration, it would be an account takeover with a
#     policy document attached.
#
# And every act of his is attributed. Her ledger says who did it, and her
# portal says so on the screen. A record that let one party's decision appear
# as another's is worse than no record: it is a record that will be believed.
#
# The credential is a short-lived token the organization signs with the key
# it publishes, naming the member and the administrator. Not a password, not
# a session, and not anything her identity provider issued — the
# administrator is a different party from her, and nothing here should be
# capable of impersonating her to her own authority.

ORG_ADMIN_TYP = "u4a-org-admin+jwt"


async def org_scope(owner: str) -> tuple[dict, dict]:
    """(the ceiling that says what it may reach, the tiers of hers it governs).

    Everything an administrator may see or touch is filtered through this.
    The organization holds the firm's book and shares it with her; it does
    not hold her brokerage account, nor an account she holds with somebody
    else, and no amount of co-administration turns one into the other.

    The envelope is returned rather than its claims because the reach is not
    the claims — see `org.reaches`. Handing out a bare list of patterns is
    what let a charter's wildcard walk into a jointly held account.
    """
    envelope = await org_envelope(owner) or {}
    tiers = {tid: t for tid, t in (await st(owner).tiers()).items()
             if org.governs(t, envelope)} if envelope.get("claims") else {}
    return envelope, tiers


def _org_blocked(record: dict | None) -> dict:
    blocked = (record or {}).get("blocked") or {}
    return {"handles": list(blocked.get("handles") or []),
            "operators": list(blocked.get("operators") or [])}


async def org_blocks_agent(owner: str, handle: str,
                           identity: dict | None = None) -> bool:
    """Whether the organization has shut this agent out of *its* resources.

    Kept in the membership record rather than beside her own revocations,
    and that is the whole design of it. Her revocations are hers and outlive
    anything; these are the organization's, they apply only to the
    organization's resources, and they vanish when the membership does.
    An administrator can stop an agent reaching the firm's book and cannot,
    by any path, touch that agent's standing with her.
    """
    blocked = _org_blocked(await org_record(owner))
    if handle in blocked["handles"]:
        return True
    origin = operator_origin(identity or {})
    return bool(origin and origin in blocked["operators"])


async def org_block(owner: str, *, handle: str = None, operator: str = None,
                    remove: bool = False) -> dict:
    record = await org_record(owner)
    if record is None:
        raise HTTPException(status_code=403, detail="not enrolled")
    blocked = _org_blocked(record)
    key, value = ("handles", handle) if handle else ("operators", operator)
    if remove:
        blocked[key] = [x for x in blocked[key] if x != value]
    elif value not in blocked[key]:
        blocked[key].append(value)
    record["blocked"] = blocked
    await st(owner).set_organization(record)
    return blocked


async def require_org_admin(request: Request, owner: str) -> dict:
    """The administrator acting on this owner, or a refusal.

    Three things have to hold and each rules out a different attack: the
    token is signed by the organization *this owner enrolled with* (not any
    organization), it names her (not a member of the same organization
    reaching sideways), and it is fresh (not one kept from a membership that
    has since ended).
    """
    if not serves(owner):
        raise HTTPException(status_code=404, detail="not an owner here")
    record = await org_record(owner)
    if record is None:
        raise HTTPException(
            status_code=403,
            detail="this owner does not administer these resources for anyone")
    token = _bearer(request)
    try:
        typ = jwt.get_unverified_header(token).get("typ")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="that is not a token")
    if typ != ORG_ADMIN_TYP:
        raise HTTPException(status_code=401,
                            detail=f"an administration token has typ {ORG_ADMIN_TYP}")
    issuer = record["issuer"]
    claims = None
    for jwk_dict in issuer_keys(issuer):
        try:
            claims = jwt.decode(token, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                algorithms=["EdDSA"], issuer=issuer,
                                options={"verify_aud": False})
            break
        except jwt.InvalidTokenError:
            continue
    if claims is None or claims.get("sub") != owner:
        raise HTTPException(
            status_code=401,
            detail="that token is not signed by this owner's organization for "
                   "this owner")
    return {"org": claims.get("org"), "name": claims.get("org_name"),
            "admin": claims.get("admin") or "an administrator"}


@app.get("/org/admin/{owner}/pending")
async def org_admin_pending(owner: str, request: Request) -> list:
    """What is waiting on her *about the organization's resources*.

    Not her queue. An agent asking to read her own brokerage account is
    nothing to do with her employer, does not appear here, and cannot be
    denied from here — which is the difference between an organization that
    shares resources with her and one that has taken over her account.
    """
    await require_org_admin(request, owner)
    envelope, _ = await org_scope(owner)
    return [p for p in await pending_view(owner)
            if org.reaches(p.get("resource_id") or "", envelope)]


@app.post("/org/admin/{owner}/pending/{family}/decision")
async def org_admin_decision(owner: str, family: str, request: Request) -> dict:
    actor = await require_org_admin(request, owner)
    envelope, _ = await org_scope(owner)
    pended = await st(owner).negotiation(family)
    if not org.reaches((pended or {}).get("resource_id") or "", envelope):
        # Both directions refused, not just approval. An administrator who
        # could deny a request about her own accounts could interfere with
        # her arrangements at will, and "it was only a refusal" is no comfort
        # when the agent being refused is her accountant's.
        raise HTTPException(
            status_code=403,
            detail="that request is about a resource your organization does "
                   "not share with this member, and is none of its business")
    return await decide_pending(owner, family, (await request.json()).get("decision"),
                                actor)


async def org_related_connections(owner: str) -> list:
    """Her agents that have anything to do with the organization.

    An agent is the organization's business when it has been granted at, or
    approved at, a tier of hers that governs one of the organization's
    resources — or is asking for one right now. Everything else is an
    arrangement between her and somebody's agent about her own accounts, and
    an administrator has no more business seeing it than her bank does.
    """
    envelope, tiers = await org_scope(owner)
    if not envelope.get("claims"):
        return []
    governed = set(tiers)
    pending_handles = {
        rec.get("handle") for rec in await st(owner).pending_negotiations()
        if org.reaches(rec.get("resource_id") or "", envelope)}
    blocked = _org_blocked(await org_record(owner))
    out = []
    for conn in await st(owner).connections():
        touched = (set(conn.get("tiers_granted") or []) |
                   set(conn.get("tiers_approved") or [])) & governed
        if touched or conn["handle"] in pending_handles:
            out.append({
                **conn,
                "org_tiers": sorted(touched),
                # Whether the organization has shut this one out of *its*
                # resources — which is not the same as her `status`, and the
                # console has to be able to tell them apart or it offers to
                # shut out an agent it has already shut out.
                "blocked_for_organization": (
                    conn["handle"] in blocked["handles"]
                    or (operator_origin(conn.get("identity") or {}) or "")
                    in blocked["operators"]),
            })
    return out


@app.get("/org/admin/{owner}/connections")
async def org_admin_connections(owner: str, request: Request) -> list:
    await require_org_admin(request, owner)
    return await org_related_connections(owner)


@app.post("/org/admin/{owner}/connections/{handle}/revoke")
async def org_admin_revoke(owner: str, handle: str, request: Request) -> dict:
    """Shut an agent out of the organization's resources.

    Not a revocation of the connection. Her relationship with this agent is
    hers — it may be reading her own portfolio for her every morning — and an
    organization that could end it would be reaching well past the resources
    it shares. So what this does is narrower and exact: the agent stops being
    able to reach anything the charter claims, immediately, and everything
    else about its standing with her is untouched.
    """
    actor = await require_org_admin(request, owner)
    if not any(c["handle"] == handle for c in await org_related_connections(owner)):
        raise HTTPException(
            status_code=404,
            detail="that agent has no dealings with your organization's "
                   "resources")
    await org_block(owner, handle=handle)
    event("org.agent_blocked", owner=owner, handle=handle,
          by=actor.get("admin"))
    await ledger_add(owner, "org_acted", "-", {
        "what": "shut an agent out of the organization's resources",
        "note": "its access to your own accounts is unchanged",
        "by": actor}, handle=handle)
    await owner_notify(owner, {"type": "decided", "family": "-",
                               "decision": "org-revoked", "by": actor})
    return {"handle": handle, "status": "blocked-for-organization"}


@app.post("/org/admin/{owner}/connections/{handle}/restore")
async def org_admin_restore(owner: str, handle: str, request: Request) -> dict:
    actor = await require_org_admin(request, owner)
    await org_block(owner, handle=handle, remove=True)
    await ledger_add(owner, "org_acted", "-", {
        "what": "let an agent reach the organization's resources again",
        "by": actor}, handle=handle)
    return {"handle": handle, "status": "allowed"}


@app.get("/org/admin/{owner}/operators")
async def org_admin_operators(owner: str, request: Request) -> list:
    """The operators behind the agents that touch the organization's
    resources, and nobody else's."""
    await require_org_admin(request, owner)
    conns = await org_related_connections(owner)
    origins = {o for o in (operator_origin(c.get("identity") or {})
                           for c in conns) if o}
    blocked = _org_blocked(await org_record(owner))["operators"]
    rows = [o for o in await operators_view(owner)
            if o["origin"] in origins or o["origin"] in blocked]
    return [{**o, "blocked_for_organization": o["origin"] in blocked}
            for o in rows]


@app.post("/org/admin/{owner}/operators/{action}")
async def org_admin_operator_action(owner: str, action: str,
                                    request: Request) -> dict:
    actor = await require_org_admin(request, owner)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if action not in ("block", "unblock"):
        raise HTTPException(status_code=404, detail="unknown action")
    await org_block(owner, operator=origin, remove=(action == "unblock"))
    event("org.operator_blocked", owner=owner, operator=origin,
          action=action, by=actor.get("admin"))
    await ledger_add(owner, "org_acted", "-", {
        "what": ("shut out every agent of an operator, for the organization's "
                 "resources" if action == "block"
                 else "let an operator's agents reach the organization's "
                      "resources again"),
        "operator": origin, "by": actor})
    await owner_notify(owner, {"type": "decided", "family": "-",
                               "decision": f"org-{action}", "by": actor})
    return {"origin": origin, "blocked_for_organization": action == "block"}


@app.get("/org/admin/{owner}/ledger")
async def org_admin_ledger(owner: str, request: Request) -> list:
    """The organization's part of her record.

    The same entries she reads, narrowed to what concerns the organization:
    its own resources, its own acts, and the moments the membership itself
    changed. Her negotiations about her own accounts are not in here.
    """
    await require_org_admin(request, owner)
    _, tiers = await org_scope(owner)
    org_kinds = {"org_joined", "org_left", "org_clamped", "org_refused",
                 "org_role", "org_acted", "break_glass"}
    handle = request.query_params.get("handle") or None
    return [e for e in await st(owner).ledger(handle)
            if e.get("kind") in org_kinds or e.get("tier") in tiers]


# --- Grant API (agent-facing, UMA 2.0 Grant shape) ---------------------------


async def terms_template_for(rec: dict, tier_id: str, tier: dict, family: str) -> dict:
    template = dict(tier["terms"])
    template.update(
        {
            "proffered_by": ISSUER,
            "terms_uri": await publish_terms(rec["owner"], tier_id, tier),
            "nonce": rec["nonce"],
            "family": family,
            "resource_id": rec["resource_id"],
        }
    )
    return template


def federated_provider(envelope: dict | None, resource_id: str) -> dict | None:
    """The identity provider to ask about this resource, or None.

    Two conditions, and both matter. The organization has to have named a
    provider in its charter — federating identity is something a member
    agreed to when she read the charter, not a default. And the resource has
    to be one the organization actually reaches: `org.reaches` already
    subtracts what she holds jointly with somebody else, so an enterprise
    provider is never consulted about a resource that is not the
    organization's to speak for. Her own accounts never reach this line.
    """
    if not envelope or not org.reaches(resource_id, envelope):
        return None
    idp = envelope.get("identity_provider") or None
    return idp if idp and idp.get("issuer") else None


# What a key of each type is allowed to have signed with. Asymmetric only —
# a provider publishing a symmetric key in a public JWKS has published its
# signing secret, and this profile will not treat that as a key.
_ALGS_BY_KTY = {
    "OKP": ["EdDSA"],
    "RSA": ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512"],
    "EC": ["ES256", "ES384", "ES512"],
}


def algs_for(jwk_dict: dict) -> list:
    """The algorithms this key may have signed with."""
    if declared := jwk_dict.get("alg"):
        # A key that names its own algorithm is taken at its word, provided
        # the word is one its type could have said.
        return [declared] if declared in _ALGS_BY_KTY.get(
            jwk_dict.get("kty"), []) else []
    return _ALGS_BY_KTY.get(jwk_dict.get("kty"), [])


_PROVIDER_TRUST: str | None = None


def provider_trust() -> str | bool:
    """What to verify an identity provider's TLS against.

    Everywhere else in this server the lab CA *replaces* the trust store,
    which is deliberate: a peer inside the lab should not be trusted because
    some public authority vouched for it. An identity provider is the one
    party that may legitimately be outside — a real tenant has an ordinary
    public certificate — so here the lab CA is *added to* the public roots
    rather than swapped for them.

    Getting this the wrong way round fails in a way that reads like the
    provider being down: discovery returns nothing and the keys never load.
    """
    global _PROVIDER_TRUST
    if _PROVIDER_TRUST is not None:
        return _PROVIDER_TRUST
    lab = org.CA_BUNDLE
    if not lab or not os.path.exists(lab):
        _PROVIDER_TRUST = True          # public roots only
        return _PROVIDER_TRUST
    try:
        import certifi
        combined = "/tmp/u4a-provider-trust.pem"
        with open(combined, "w") as out:
            out.write(open(certifi.where()).read())
            out.write("\n")
            out.write(open(lab).read())
        _PROVIDER_TRUST = combined
    except Exception:                                           # noqa: BLE001
        # No public roots available; the lab CA alone still serves a provider
        # hosted inside the lab, which is the shipped arrangement.
        _PROVIDER_TRUST = lab
    return _PROVIDER_TRUST


_PROVIDER_META: dict[str, tuple[float, dict]] = {}
_PROVIDER_JWKS: dict[str, tuple[float, list]] = {}


def provider_metadata(issuer: str) -> dict:
    """An identity provider's own description of itself.

    Fetched rather than constructed, because the endpoints are not derivable.
    A real tenant's token endpoint is `/oauth2/v1/token` under the org, not
    `{issuer}/token` — so an authority that built the URL itself would send
    every agent to a 404 and the failure would look like the agent's.
    """
    import httpx

    cached = _PROVIDER_META.get(issuer)
    if cached and cached[0] > now():
        return cached[1]
    base = issuer.rstrip("/")
    doc = {}
    with httpx.Client(verify=provider_trust(), timeout=5.0) as client:
        for url in (f"{base}/.well-known/openid-configuration",
                    f"{base}/.well-known/oauth-authorization-server"):
            try:
                r = client.get(url)
                if r.status_code == 200 and r.json().get("issuer"):
                    doc = r.json()
                    break
            except Exception:                                   # noqa: BLE001
                continue
    _PROVIDER_META[issuer] = (now() + 300, doc)
    return doc


def provider_keys(issuer: str, fresh: bool = False) -> list:
    """An identity provider's signing keys.

    Discovery first, `{issuer}/jwks` only as a fallback. The fallback is this
    lab's own convention and nothing else publishes keys there; a real tenant
    advertises `jwks_uri` in its OpenID metadata and will not have heard of
    it. Getting this the right way round is the difference between the
    profile working against an actual identity provider and working only
    against the one shipped beside it.
    """
    import httpx

    cached = _PROVIDER_JWKS.get(issuer)
    if cached and cached[0] > now() and not fresh:
        return cached[1]
    base = issuer.rstrip("/")
    keys = []
    with httpx.Client(verify=provider_trust(), timeout=5.0) as client:
        if jwks_uri := provider_metadata(issuer).get("jwks_uri"):
            try:
                doc = client.get(jwks_uri)
                doc.raise_for_status()
                keys = doc.json().get("keys") or []
            except Exception:                                   # noqa: BLE001
                keys = []
        if not keys:
            doc = client.get(f"{base}/jwks")
            doc.raise_for_status()
            keys = doc.json().get("keys") or []
    _PROVIDER_JWKS[issuer] = (now() + 300, keys)
    return keys


def verify_id_jag(assertion: str, idp: dict, owner: str, resource_id: str) -> dict:
    """An identity provider's assertion about who an agent acts for.

    What is checked here is *only* identity and reach. Nothing in an ID-JAG
    decides anything about the resource — that is the next beat, and it is
    this owner's to decide.
    """
    issuer = idp["issuer"]
    try:
        head = jwt.get_unverified_header(assertion)
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"that is not an assertion: {exc}")
    # A plain JWT signed by the same provider is not an identity assertion,
    # and treating one as if it were would accept any token the provider ever
    # issued for any purpose. The media type is the difference.
    if head.get("typ") != ID_JAG_TYP:
        raise ValueError(
            f"expected an ID-JAG (typ {ID_JAG_TYP}), got typ {head.get('typ')!r}")

    # A provider nobody can reach is a provider that has not vouched for
    # anybody. Refused rather than raised: the resource is the organization's,
    # and the direction to fail in is the same one an unreadable ceiling fails
    # in — see `organization_blocks`.
    try:
        keys = provider_keys(issuer)
        kid = head.get("kid")
        if kid and not any(k.get("kid") == kid for k in keys):
            keys = provider_keys(issuer, fresh=True)  # rotated, not forged
    except Exception as exc:                                    # noqa: BLE001
        raise ValueError(
            f"{issuer} could not be reached to check the assertion") from exc
    # Signature first, claims second, and reported separately.
    #
    # Folding them together is tempting and costs hours: an assertion minted
    # for a different audience then reports as "does not verify against the
    # provider", which sends whoever is debugging it to the keys — the one
    # thing that was never wrong.
    claims = None
    signature_error = None
    for jwk_dict in keys:
        if kid and jwk_dict.get("kid") != kid:
            continue
        try:
            # Whatever the provider actually signs with — an RSA tenant and
            # an Ed25519 one are the same code path here.
            #
            # The permitted algorithms come from the *key*, never from the
            # token's own header: a token that nominated its own algorithm
            # would be choosing how it gets checked.
            key = jwt.PyJWK(jwk_dict)
            claims = jwt.decode(
                assertion, key.key, algorithms=algs_for(jwk_dict),
                options={"verify_aud": False, "verify_iss": False})
            break
        except jwt.InvalidTokenError as exc:
            signature_error = exc
            continue
    if claims is None:
        raise ValueError(
            f"the assertion's signature does not verify against {issuer}"
            + (f": {signature_error}" if signature_error else ""))

    if claims.get("iss") != issuer:
        raise ValueError(
            f"the assertion is from {claims.get('iss')!r}, and this "
            f"organization federates to {issuer!r}")
    # The audience check is what stops an assertion minted for one member's
    # authority being spent at another's. The provider audiences each one
    # deliberately; honouring that is the whole of this server's side of the
    # bargain.
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else list(aud or [])
    if ISSUER not in audiences:
        raise ValueError(
            f"the assertion is audienced at {audiences or ['nothing']} and "
            f"this authority is {ISSUER!r} — the resource application's "
            f"audience at the provider has to be this authority")

    jti = claims.get("jti") or ""
    if not jti:
        raise ValueError("the assertion has no jti and cannot be spent once")
    for spent, expires in list(_ID_JAG_SPENT.items()):
        if expires < now():
            _ID_JAG_SPENT.pop(spent, None)
    if jti in _ID_JAG_SPENT:
        raise ValueError("that assertion has already been used")

    # Whose agent it is has to be whose authority this is. The audience check
    # above says the assertion was meant for this server; this says it was
    # meant for this server *about this member*. Without it, an assertion for
    # one employee would open a negotiation over another's administration.
    # Which claim names the person. `preferred_username` is what this lab's
    # provider sends; a real tenant may only send `sub` and `email`, and the
    # charter can name the claim it uses. All of them are compared against the
    # owner this authority serves, so a provider that sends several cannot
    # have one of them quietly disagree.
    named = (idp.get("subject_claim")
             and [claims.get(idp["subject_claim"])]
             or [claims.get("preferred_username"), claims.get("email"),
                 (claims.get("email") or "").split("@")[0], claims.get("sub")])
    if owner not in [n for n in named if n]:
        raise ValueError(
            f"the assertion names {[n for n in named if n][:1] or ['nobody']} "
            f"and this authority is {owner!r}'s")

    # And the enterprise's own ceiling: the administrator approved this
    # application for particular operations at that resource. This is the
    # first of three, and the only one the organization sets — the charter
    # sets the second and her terms set the third.
    operation = resource_id.split("/", 1)[-1]
    granted = (claims.get("scope") or "").split()
    if operation not in granted:
        raise ValueError(
            f"{claims.get('iss')} did not approve this application for "
            f"{operation!r} — it carries {granted or ['nothing']}")

    _ID_JAG_SPENT[jti] = float(claims.get("exp") or (now() + 300))
    return claims


async def need_identity_response(rec: dict, idp: dict) -> JSONResponse:
    """Beat 1a: before terms, who is this agent acting for?

    Asked *first* because the answer decides what comes next. Which tier
    applies and what her terms may say both follow from which member the
    agent acts for, so dictating terms before knowing would be dictating them
    to nobody in particular.

    This is also the whole of what makes the exchange resource-server
    initiated. The agent arrives knowing nothing about Northwind; it is told
    which provider to go to, what to name as the audience and the resource,
    and which scope to ask for. Nothing was pre-arranged with the agent, and
    no provider pushed anything at it.
    """
    rec["state"] = "need_identity"
    rotated = await new_ticket(rec)
    operation = rec["resource_id"].split("/", 1)[-1]
    try:
        meta = provider_metadata(idp["issuer"])
    except Exception:                                           # noqa: BLE001
        meta = {}
    event("need_info.identity_required", corr=rec["family"],
          provider=idp["issuer"], resource_id=rec["resource_id"])
    return JSONResponse(
        {
            "error": "need_info",
            "ticket": rotated,
            "required_claims": [
                {
                    "claim_type": ID_JAG_CLAIM,
                    "claim_token_format": [ID_JAG_FORMAT],
                    "friendly_name": "who your organization says you act for",
                    # Everything needed to go and get one. An agent that has
                    # never heard of this organization can complete the next
                    # step from this object alone.
                    "identity_provider": {
                        "issuer": idp["issuer"],
                        # Discovered, not constructed. See provider_metadata.
                        "token_endpoint": (meta.get("token_endpoint")
                                           or f"{idp['issuer'].rstrip('/')}/token"),
                        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                        "requested_token_type": ID_JAG_FORMAT,
                        # What this provider will exchange. A tenant takes a
                        # refresh token from the employee's sign-in; the one
                        # shipped beside this lab takes an ID token. An agent
                        # holds whichever its provider issued it, so the list
                        # travels rather than a single assumed value.
                        "subject_token_types_supported":
                            meta.get("subject_token_types_supported")
                            or ["urn:ietf:params:oauth:token-type:id_token",
                                "urn:ietf:params:oauth:token-type:refresh_token"],
                    },
                    "audience": ISSUER,
                    "resource": RS_RESOURCE_URI,
                    "scope": [operation],
                }
            ],
        },
        status_code=403,
    )


async def need_info_response(rec: dict, tier_id: str, tier: dict) -> JSONResponse:
    family = rec["family"]
    rec["state"] = "need_info"
    rec["nonce"] = secrets.token_urlsafe(12)
    rec["tier"] = tier_id
    template = await terms_template_for(rec, tier_id, tier, family)
    rec["template"] = template
    rotated = await new_ticket(rec)
    event("need_info.terms_dictated", corr=family, tier=tier_id,
          template_id=template["template_id"], resource_id=rec["resource_id"])
    return JSONResponse(
        {
            "error": "need_info",
            "ticket": rotated,
            "required_claims": [
                {
                    "claim_type": AGREEMENT_CLAIM,
                    "claim_token_format": [AGREEMENT_FORMAT],
                    "friendly_name": f"Alice's terms: {tier['name']}",
                    "terms_template": template,
                }
            ],
        },
        status_code=403,
    )


AGENT_ISSUER_CA = os.environ.get("UMA4A_CA_BUNDLE")  # trust bundle for issuer TLS
_ISSUER_JWKS_CACHE: dict[str, tuple[float, list]] = {}
JWKS_CACHE_TTL = 300


def agent_issuer_keys(iss: str) -> list:
    """Resolve an agent-token issuer's signing keys via AAuth discovery
    (GET {iss}/.well-known/aauth-agent.json -> jwks_uri). TLS on the issuer
    origin is the trust root — AAuth's own precondition — so non-https
    issuers are rejected outright."""
    if not iss.startswith("https://"):
        raise ValueError("agent token issuer must be an https origin")
    cached = _ISSUER_JWKS_CACHE.get(iss)
    if cached and cached[0] > now():
        return cached[1]
    import httpx

    with httpx.Client(verify=AGENT_ISSUER_CA or True, timeout=5.0) as client:
        meta = client.get(f"{iss}/.well-known/aauth-agent.json")
        meta.raise_for_status()
        jwks = client.get(meta.json()["jwks_uri"])
        jwks.raise_for_status()
    keys = jwks.json()["keys"]
    _ISSUER_JWKS_CACHE[iss] = (now() + JWKS_CACHE_TTL, keys)
    return keys


def verify_agent_token(agent_token: str) -> dict:
    """Validate an aa-agent+jwt against its issuer's published keys.
    Returns the verified claims; raises on any break in the chain."""
    header = jwt.get_unverified_header(agent_token)
    if header.get("typ") != "aa-agent+jwt":
        raise ValueError(f"agent token typ must be aa-agent+jwt, got {header.get('typ')!r}")
    unverified = jwt.decode(agent_token, options={"verify_signature": False})
    iss = unverified.get("iss")
    if not iss:
        raise ValueError("agent token has no issuer")
    try:
        candidates = agent_issuer_keys(iss)
    except Exception as exc:
        raise ValueError(f"agent token issuer discovery failed for {iss}: {exc}")
    kid = header.get("kid")
    last_error: Exception | None = None
    for jwk_dict in candidates:
        if kid and jwk_dict.get("kid") and jwk_dict["kid"] != kid:
            continue
        try:
            key = OKPAlgorithm.from_jwk(json.dumps(jwk_dict))
            claims = jwt.decode(agent_token, key, algorithms=["EdDSA"],
                                options={"verify_aud": False})
            if "cnf" not in claims or "jwk" not in claims["cnf"]:
                raise ValueError("agent token carries no cnf.jwk key binding")
            return claims
        except jwt.InvalidTokenError as exc:
            last_error = exc
    raise ValueError(f"agent token signature did not verify against {iss}'s "
                     f"published keys: {last_error}")


def connection_handle(identity: dict, signer_jwk: dict) -> str:
    """The stable name for a standing relationship. A pseudonymous agent *is*
    its key, so the RFC 7638 thumbprint is the handle. An identified agent's
    continuity lives in its issuer+subject — its session keys rotate, and a
    thumbprint-keyed connection would forget the agent every session."""
    if identity.get("level") == "identified":
        from urllib.parse import urlparse

        sub, host = identity["sub"], urlparse(identity["iss"]).netloc
        # Qualify by issuer so two issuers' subjects can never collide —
        # unless the issuer already writes its host into the subject.
        return sub if sub.endswith(f"@{host}") else f"{sub}@{host}"
    return jwk_thumbprint(signer_jwk)


async def first_party_fact(owner: str, identity: dict, axes: dict) -> bool:
    """Did Alice activate this agent herself?

    Two halves, and both are required. The operator the agent names has to be
    an origin she claimed, and her authority has to have found this agent's
    signing key in that operator's own key directory.

    Dropping the second half would be fatal rather than merely weaker. A
    Client ID Metadata Document proves only that it claims the URL it was
    fetched from, so any agent may point at one she publishes and reach
    accountability level 1. Only she can put a key in her directory, which is
    what makes level 2 a fact about *this agent* rather than about her.

    That is also why this may relax a requirement at all: the claim is her
    decision, the attestation is her authority's own check, and the requesting
    side has no hand in either.
    """
    if axes.get("accountability") != assurance.ACCOUNTABILITY_ATTESTED:
        return False
    origin = operator_origin(identity)
    return origin is not None and origin in await st(owner).owned_operators()


def standing_facts(conn: dict | None, tier_id: str,
                   trajectory: dict | None = None,
                   first_party: bool = False) -> dict:
    """What Alice's own authority has seen of this agent.

    Kept apart from assurance because only these may relax a requirement —
    they are the one kind of evidence here that the requesting side had no
    hand in producing. `age_seconds` is None when she has never met it, which
    the conditions read as "younger than everything, older than nothing".

    `trajectory` and `first_party` are read by the caller and passed in, so
    `policy.evaluate` stays a pure function of a dict and can be tested with
    no store at all.
    """
    trajectory = trajectory or {"denials": 0, "tiers": []}
    if conn is None or conn.get("status") != "active":
        return {"active": False, "age_seconds": None, "first_at_tier": True,
                "first_party": first_party,
                "approved_tiers": [], "trajectory": trajectory,
                "revocations": int((conn or {}).get("revocations", 0))}
    age = None
    if first_seen := conn.get("first_seen"):
        try:
            age = max(0, int(now() - calendar.timegm(
                time.strptime(first_seen, "%Y-%m-%dT%H:%M:%SZ"))))
        except ValueError:
            age = None
    return {
        "active": True,
        "age_seconds": age,
        # What this server did.
        "first_party": first_party,
        "first_at_tier": tier_id not in (conn.get("tiers_granted") or []),
        # What Alice decided. Only these may lower a requirement, so they are
        # kept apart from the line above even though both are her side's.
        "approved_tiers": list(conn.get("tiers_approved") or []),
        "revocations": int(conn.get("revocations", 0)),
        # What it has been doing lately. Restrictions only — see policy.py.
        "trajectory": trajectory,
    }


async def trajectory_facts(owner: str, handle: str) -> dict:
    """This agent's recent history, from the ledger her decisions already
    wrote. No counters, no second source of truth.

    Not one of the store's indivisible operations, and it does not need to be:
    the count only ever tightens a requirement, so a replica reading one write
    stale behaves as if the request had arrived a moment earlier — an ordering
    the system already permits. The rule of thumb worth keeping: can a stale
    read widen access beyond what a differently-timed arrival would have? If it
    can, it belongs with the single-use operations instead.
    """
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          time.gmtime(now() - policy.parse_duration(TRAJECTORY_WINDOW)))
    return await st(owner).trajectory(handle, since)


# Cached, but not forever. An operator removing a key from its directory is
# how it stops vouching for an agent, and a cache with no expiry would keep
# attesting one it had disowned. Bounded as well as timed: the URL is named by
# the requesting side, so an unbounded map is something an agent can grow.
_DIRECTORY_TTL = float(os.environ.get("UMA_AS_DIRECTORY_TTL", "300"))
_DIRECTORY_MAX = 256
_DIRECTORY_CACHE: dict[str, tuple[float, list]] = {}


def operator_origin(identity: dict) -> str | None:
    """The origin of the operator an agent names, or None if it names none.

    Origin rather than the full client_id URL, because an operator publishing
    two metadata documents is still one party — and because the origin is what
    the key-directory check already has to match.
    """
    from urllib.parse import urlparse

    meta = identity.get("client_metadata") or {}
    client_id = meta.get("client_id")
    if not client_id:
        return None
    p = urlparse(client_id)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


def same_origin(a: str, b: str) -> bool:
    from urllib.parse import urlparse

    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc) and pa.scheme == "https"


def operator_published_key(client_id: str, directory: str,
                           signer_jwk: dict) -> bool:
    """Did the operator named by `client_id` publish this signing key?

    A Web Bot Auth key directory (draft-meunier-http-message-signatures-
    directory) is a JWKS of the keys an operator's agents sign with. Fetching
    it and looking for this key's RFC 7638 thumbprint is a check this server
    performs itself, against a document the *operator* controls and the agent
    does not.

    Two things keep it honest:

    * **Same origin as the client_id.** Otherwise an agent points at a
      directory it runs and attests to itself, which is not an attestation.
    * **Failure is not an accusation.** An unreachable directory leaves the
      claim exactly where it was — self-asserted — rather than counting
      against the agent. Availability of a third party is not evidence about
      the agent, and treating it as such makes any operator's outage look
      like an attack.
    """
    import httpx

    if not same_origin(client_id, directory):
        event("operator_directory.rejected", client_id=client_id,
              directory=directory, reason="not same origin as client_id")
        return False
    def fetch() -> list:
        r = httpx.get(directory, timeout=5.0, follow_redirects=False,
                      verify=AGENT_ISSUER_CA or True)
        r.raise_for_status()
        keys = r.json().get("keys") or []
        if len(_DIRECTORY_CACHE) >= _DIRECTORY_MAX:
            _DIRECTORY_CACHE.pop(next(iter(_DIRECTORY_CACHE)), None)
        _DIRECTORY_CACHE[directory] = (now(), keys)
        return keys

    try:
        wanted = jwk_thumbprint(signer_jwk)

        def holds(keys: list) -> bool:
            for k in keys:
                try:                   # a directory may hold key types we do
                    if jwk_thumbprint(k) == wanted:   # not profile; skip them
                        return True
                except (KeyError, TypeError):
                    continue
            return False

        # Only a *hit* may be served from cache. A miss is re-fetched, because
        # the two errors are not the same size: a stale hit keeps attesting a
        # key the operator has disowned, while a stale miss merely fails to
        # recognise one it has just published — which is the common case, since
        # an agent enrols and then immediately negotiates. So the TTL bounds
        # how long a withdrawal takes to land, and a newly published key is
        # picked up on the next request rather than in five minutes.
        cached = _DIRECTORY_CACHE.get(directory)
        fresh = cached is not None and now() - cached[0] < _DIRECTORY_TTL
        found = fresh and holds(cached[1])
        if not found:
            found = holds(fetch())
        event("operator_directory.checked", directory=directory,
              published=found, from_cache=bool(fresh and found))
        return found
    except Exception as exc:                                       # noqa: BLE001
        event("operator_directory.unresolved", directory=directory,
              reason=str(exc)[:120])
        return False



# --- resource server establishment ---------------------------------------
#
# FedAuthz starts from a resource server that already holds a PAT and says
# nothing about how it came to. Where one operator runs both sides that gap is
# closed by configuration, and a seeded client secret is a fair model of it.
# It stops being closable that way as soon as the authority is the owner's:
# she is not going to paste a secret into her brokerage's console, and the
# brokerage is not going to hold one secret per customer.
#
# So the resource server authenticates as its origin. It signs with a key it
# publishes at that origin, in the RFC 9728 document it already has to serve,
# and this server fetches that document itself. Nothing is provisioned ahead
# of time and no secret is ever transmitted. What is being trusted is control
# of the origin — which is what the address in her challenge pointed at
# anyway, so the check adds no new party to trust.

_RS_META_TTL = float(os.environ.get("UMA_AS_RS_META_TTL", "300"))
_RS_META_CACHE: dict[str, tuple[float, dict]] = {}
# How long a resource that did not check out stays refused without being
# re-fetched, and how big a document may be.
#
# This endpoint takes no credential — that is the point of it — so anyone can
# make this server fetch a URL they chose. Two bounds on what that is worth:
# a failure is remembered briefly, so a flood of bad registrations does not
# become a flood of outbound requests, and a response is read up to a cap
# rather than into memory.
#
# Deliberately the opposite of the operator key directory, which caches only
# hits. There, a stale miss would fail to recognise a key an operator just
# published, in the common case where an agent enrols and immediately
# negotiates — a real cost for no gain, since that check is an attestation.
# Here the fetch *is* the authentication and a registration is retried by a
# resource server rather than awaited by a person, so a few seconds of
# remembered "no" costs nothing and is the only thing bounding the amplifier.
_RS_MISS_TTL = float(os.environ.get("UMA_AS_RS_MISS_TTL", "30"))
_RS_MAX_BYTES = int(os.environ.get("UMA_AS_RS_MAX_BYTES", "65536"))
_RS_MISS_CACHE: dict[str, float] = {}


def _fetch_json(url: str, what: str) -> dict | None:
    """GET a document this server was told to fetch, bounded. None on any
    failure, which every caller reads as "not authenticated"."""
    import httpx

    try:
        with httpx.Client(timeout=5.0, follow_redirects=False,
                          verify=AGENT_ISSUER_CA or True) as c:
            with c.stream("GET", url) as r:
                r.raise_for_status()
                size = 0
                chunks = []
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > _RS_MAX_BYTES:
                        raise ValueError(f"over {_RS_MAX_BYTES} bytes")
                    chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except Exception as exc:                                       # noqa: BLE001
        event(f"resource_server.{what}", url=url, reason=str(exc)[:120])
        return None


def resource_server_metadata(resource_uri: str) -> dict:
    """The RFC 9728 document the named resource publishes about itself.

    Three things have to hold, and each closes a way of registering as
    somebody else:

    * the document claims *this* `resource` — so a host cannot publish
      metadata about a resource it does not serve;
    * its `jwks_uri` is same-origin — so the keys come from the party being
      identified rather than one it points at;
    * it names *this* authorization server — so a resource server cannot
      register with an authority it does not send its own callers to.

    Unlike the operator key directory, an unreachable document here is a
    refusal rather than a shrug. That check attests a claim already made by
    other means; this one *is* the authentication, and a credential that
    cannot be fetched has not been presented.
    """
    from urllib.parse import urlparse

    cached = _RS_META_CACHE.get(resource_uri)
    if cached and now() - cached[0] < _RS_META_TTL:
        return cached[1]
    missed = _RS_MISS_CACHE.get(resource_uri)
    if missed is not None and now() - missed < _RS_MISS_TTL:
        return {}

    def refuse() -> dict:
        if len(_RS_MISS_CACHE) >= 1024:
            _RS_MISS_CACHE.pop(next(iter(_RS_MISS_CACHE)), None)
        _RS_MISS_CACHE[resource_uri] = now()
        return {}

    p = urlparse(resource_uri)
    if p.scheme != "https" or not p.netloc:
        return refuse()
    origin = f"{p.scheme}://{p.netloc}"
    url = (f"{origin}/.well-known/oauth-protected-resource"
           f"{p.path.rstrip('/')}")
    doc = _fetch_json(url, "metadata_unreachable")
    if not isinstance(doc, dict):
        return refuse()

    reasons = []
    if doc.get("resource") != resource_uri:
        reasons.append(f"claims resource {doc.get('resource')!r}")
    jwks_uri = doc.get("jwks_uri") or ""
    if not jwks_uri or not same_origin(jwks_uri, resource_uri):
        reasons.append(f"jwks_uri {jwks_uri!r} is not same-origin")
    if ISSUER not in (doc.get("authorization_servers") or []):
        reasons.append("does not name this authorization server")
    if reasons:
        event("resource_server.metadata_rejected", resource_uri=resource_uri,
              reasons=reasons)
        return refuse()

    if len(_RS_META_CACHE) >= 256:
        _RS_META_CACHE.pop(next(iter(_RS_META_CACHE)), None)
    _RS_META_CACHE[resource_uri] = (now(), doc)
    return doc


def resource_server_keys(resource_uri: str) -> list:
    """The public keys the named resource publishes, as JWKs. Empty on any
    failure, which the callers all read as "not authenticated"."""
    doc = resource_server_metadata(resource_uri)
    if not doc:
        return []
    keys = _fetch_json(doc["jwks_uri"], "jwks_unreachable")
    if not isinstance(keys, dict):
        return []
    found = keys.get("keys")
    return found if isinstance(found, list) else []


async def verify_resource_server_signature(request: Request, body: bytes,
                                           resource_uri: str) -> bool:
    """Did the origin behind `resource_uri` sign this request?

    Off the event loop, because deciding it means dereferencing a host named
    by the caller. This runs on the PAT path, which every resource server
    takes on every refresh; a five-second timeout awaited inline would let one
    slow origin stall every other request this worker is serving.

    Every key that origin publishes is tried, because key rotation overlaps:
    a resource server that has just published a new one may still be signing
    with the old for the length of a deploy. Trying all of them accepts any
    key the origin currently vouches for and no others, which is the same
    answer a kid lookup gives without failing on a stale cache.
    """
    from uma4a_http_sig import VerifyError
    from uma4a_http_sig import verify as verify_sig

    sig_input = request.headers.get("signature-input")
    sig = request.headers.get("signature")
    if not sig_input or not sig:
        return False
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    keys = await asyncio.to_thread(resource_server_keys, resource_uri)
    for jwk in keys:
        try:
            key = OKPAlgorithm.from_jwk(json.dumps(jwk))
        except Exception:                                          # noqa: BLE001
            continue                       # a JWKS may hold types we do not
        try:                               # profile; those are simply not it
            verify_sig(
                method=request.method,
                authority=AS_AUTHORITY,
                path=path,
                authorization=request.headers.get("authorization", ""),
                signature_input=sig_input,
                signature=sig,
                public_key=key,
                body=body if body else None,
                require_digest=bool(body),
                digest_header=request.headers.get("content-digest"),
            )
            return True
        except VerifyError:
            continue
    return False


_CIMD_CACHE: dict[str, dict] = {}


def resolve_client_id(client_id: str) -> dict:
    """Fetch and validate a Client ID Metadata Document.

    Per draft-ietf-oauth-client-id-metadata-document the client_id is an https
    URL and the document it resolves to MUST claim that same URL as its own
    `client_id` — otherwise any site could publish metadata about someone
    else's agent. Everything here is display-only, so a failure downgrades to
    "unresolved" rather than rejecting the contract; what it must never do is
    silently present unverified claims as though they were checked.
    """
    import httpx

    if client_id in _CIMD_CACHE:
        return _CIMD_CACHE[client_id]
    out: dict = {"client_id": client_id, "verified": False}
    try:
        if not client_id.startswith("https://"):
            raise ValueError("client_id must be an https URL")
        r = httpx.get(client_id, timeout=5.0, follow_redirects=False,
                      verify=AGENT_ISSUER_CA or True)
        r.raise_for_status()
        doc = r.json()
        if doc.get("client_id") != client_id:
            raise ValueError("document does not claim the URL it was fetched from")
        out = {
            "client_id": client_id,
            "verified": True,
            "client_name": doc.get("client_name"),
            "client_uri": doc.get("client_uri"),
            "logo_uri": doc.get("logo_uri"),
            "policy_uri": doc.get("policy_uri"),
            "tos_uri": doc.get("tos_uri"),
            "contacts": doc.get("contacts"),
        }
        event("client_metadata.resolved", client_id=client_id,
              client_name=out.get("client_name"))
        # Only successes are cached: caching a transient failure would keep an
        # agent nameless in Alice's dialog long after its operator recovered.
        _CIMD_CACHE[client_id] = out
    except Exception as exc:
        out["error"] = str(exc)[:120]
        event("client_metadata.unresolved", client_id=client_id, reason=str(exc)[:120])
    return out


def contract_identity(claim_token_b64: str,
                      audience: str) -> tuple[dict, dict, dict]:
    """Verify an intent contract's signature and establish who signed it.

    Returns (contract_claims, signer_jwk, identity). Split out of
    `verify_contract` because a second caller needs exactly this half and
    none of the half that follows it: when a resource is held jointly, the
    agent signs one folded document addressed to the party that folded it,
    and each co-owner's authority then verifies that same JWS for itself.
    The audience differs; establishing who is asking does not, and it is the
    subtlest code here — identity levels, CIMD resolution, whether the named
    operator actually published this key. A second implementation of it would
    be a second set of answers to "how sure are we who this is".
    """
    raw = base64.urlsafe_b64decode(claim_token_b64 + "=" * (-len(claim_token_b64) % 4))
    token = raw.decode()
    header = jwt.get_unverified_header(token)

    if "jwk" in header:
        signer_jwk = header["jwk"]
        identity = {"level": "pseudonymous"}
    elif "agent_token" in header:
        agent_claims = verify_agent_token(header["agent_token"])
        signer_jwk = agent_claims["cnf"]["jwk"]
        identity = {"level": "identified", "iss": agent_claims["iss"],
                    "sub": agent_claims.get("sub")}
    else:
        raise ValueError("contract JWS must carry jwk or agent_token in its header")

    # A CIMD URL, if offered, tells Alice *who operates* this agent. It is
    # resolved and shown, never trusted: the connection handle below is still
    # the key or the verified issuer subject, so a self-asserted name can
    # never widen access. A resolution failure is not a contract failure.
    if client_id := header.get("client_id"):
        identity["client_metadata"] = resolve_client_id(client_id)
        # And, if the agent names the operator's key directory, check whether
        # that operator has published *this* key. That is the difference
        # between "a firm says it operates this agent" and "that firm
        # published this agent's key", and it is the only thing here that
        # makes accountability more than self-assertion.
        #
        # The same-origin requirement is what makes it an attestation *by the
        # named operator*: without it an agent could point at any directory it
        # controls and attest to itself.
        if directory := header.get("signature_agent"):
            identity["operator_attested"] = operator_published_key(
                client_id, directory, signer_jwk)

    key = OKPAlgorithm.from_jwk(json.dumps(signer_jwk))
    contract = jwt.decode(token, key, algorithms=["EdDSA"], audience=audience)
    # The signature verified against a key this server can name and will
    # recognise again. Recorded rather than assumed: `assurance.assess` reads
    # this, so the binding level is an observation and not a comment about the
    # call path. See assurance.py.
    identity["key_bound"] = True
    return contract, signer_jwk, identity


def verify_contract(claim_token_b64: str, rec: dict) -> tuple[dict, dict]:
    """Verify the contract *and* its echo of the terms this server dictated.

    Returns (contract_claims, signer_jwk). Everything below the split is
    about one negotiation this server is running: the nonce it issued, the
    template it proffered, and that nothing in the document came back
    weakened.
    """
    contract, signer_jwk, identity = contract_identity(claim_token_b64, ISSUER)

    template = rec["template"]
    if contract.get("nonce") != template["nonce"]:
        raise ValueError("nonce mismatch")
    if contract.get("family") != rec["family"]:
        raise ValueError("negotiation family mismatch")
    if contract.get("template_id") != template["template_id"]:
        raise ValueError("template version mismatch")
    if contract.get("terms_uri") != template["terms_uri"]:
        raise ValueError("agreement must name the proffered terms document")
    if contract.get("purpose") != template["purpose"]:
        raise ValueError("purpose was altered")
    if not set(template["prohibited"]).issubset(set(contract.get("prohibited", []))):
        raise ValueError("prohibited-actions list was weakened")
    if contract.get("expires_in", 0) > template["expires_in"]:
        raise ValueError("expiry was extended beyond dictated terms")
    if template.get("per_operation") and not contract.get("operation"):
        raise ValueError("per-operation tier requires a proposed operation in the contract")

    # The one claim the requesting side authors. It is bounded and nothing
    # else: not compared to her purpose, not parsed, not scored. Reading it
    # would put a judgement about natural language inside the grant, which
    # would make the same request answerable two ways and end the property
    # `make flow-check` asserts. It is checked for size because it is stored
    # and shown to her, and because a field with no ceiling is a place to put
    # a megabyte.
    if (reason := contract.get("reason")) is not None:
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        if len(reason.encode()) > MAX_REASON:
            raise ValueError(
                f"reason exceeds the permitted length ({MAX_REASON} bytes)")

    # A citation, checked for shape and nothing else. Whether this request is
    # inside the mission it names is the approver's question, not hers — she
    # has no standing to read Bob's mandate and rule on it, and her authority
    # could not resolve it if it wanted to (AAuth serves missions to admins
    # only). What it establishes is narrower and still worth having: somebody
    # on the other side is running a mandate at all.
    if (mission := contract.get("mission")) is not None:
        if not isinstance(mission, dict):
            raise ValueError("mission must be an object")
        approver, digest = mission.get("approver"), mission.get("s256")
        if not isinstance(approver, str) or not approver.startswith("https://"):
            raise ValueError("mission.approver must be an https URL")
        if not isinstance(digest, str) or not (16 <= len(digest) <= 128):
            raise ValueError("mission.s256 must be a content hash")
        # Normalised down to the two fields AAuth's own header carries, so a
        # citation with extra baggage cannot use her ledger as storage.
        contract["mission"] = {"approver": approver, "s256": digest}

    contract["_identity"] = identity
    return contract, signer_jwk


async def issue_rpt(rec: dict, contract_hash: str, signer_jwk: dict,
                    operation: dict | None) -> dict:
    family = rec["family"]
    owner = rec["owner"]
    tier = (await st(owner).tiers())[rec["tier"]]
    exp = int(now()) + min(3600, tier["terms"]["expires_in"])
    jti = f"rpt_{uuid.uuid4().hex[:12]}"
    claims = {
        "iss": ISSUER,
        "sub": rec.get("agent_sub", "aauth:pseudonymous-agent"),
        # Whose resources this grant is against. `sub` is the agent, so
        # without this a multi-tenant server has nothing on an introspection
        # request that says which owner's registry to consult.
        "owner": owner,
        "aud": "https://gateway.uma.lab",
        "jti": jti,
        "exp": exp,
        "cnf": {"jwk": signer_jwk},
        "permissions": [
            {
                "resource_id": rec["resource_id"],
                "resource_scopes": rec["resource_scopes"],
                "exp": int(now()) + tier["terms"]["expires_in"],
            }
        ],
        "contract": contract_hash,
    }
    if operation is not None:
        claims["single_use"] = True
        claims["operation"] = {
            "tool": operation["tool"],
            "params_s256": s256(json.dumps(operation.get("params", {}), sort_keys=True).encode()),
        }
    token = jwt.encode(claims, SIGNING_KEY, algorithm="EdDSA",
                       headers={"typ": "aa-auth+jwt", "kid": KID})
    handle = connection_handle(rec["contract"]["_identity"], signer_jwk)
    await st(owner).record_rpt(jti, family, handle, claims.get("operation"),
                               rec["tier"])
    event("rpt.issued", corr=family, jti=jti, single_use=claims.get("single_use", False),
          tier=rec["tier"])

    # MyTerms pattern (IEEE 7012 5.2.2/5.4.4): identical, dually-signed
    # copies on both sides. The receipt embeds the complete agent-signed
    # agreement JWS and is counter-signed by the AS, so the artifact the
    # agent stores and the one Alice's side stores are the same record.
    receipt = jwt.encode(
        {
            "iss": ISSUER,
            "sub": handle,
            "iat": int(now()),
            "family": family,
            "terms_uri": rec["template"]["terms_uri"],
            "template_id": rec["template"]["template_id"],
            "agreement": contract_hash,
            "agreement_jws": rec.get("agreement_jws"),
        },
        SIGNING_KEY,
        algorithm="EdDSA",
        headers={"typ": "myterms-receipt+jws", "kid": KID},
    )
    rec["receipt"] = receipt
    event("receipt.issued", corr=family, agreement=contract_hash)
    return {"access_token": token, "token_type": "PoP",
            "expires_in": exp - int(now()), "receipt": receipt}


# --- Resources held jointly with somebody else -------------------------------
#
# One resource, several owners, none above the others. The counting happens
# somewhere else — at a tally that holds no policy — and what this server
# contributes is a signed answer about one negotiation. Two properties are
# worth holding on to while reading:
#
#   * nothing here answers a party this owner has not agreed to deal with;
#   * nothing the tally says is taken on trust. It relays the agent's signed
#     agreement and this server verifies it, folds nothing and is checked
#     against her own terms when it claims to have folded faithfully.


def joint_verdict_jws(claims: dict) -> str:
    return jwt.encode({**claims, "iss": ISSUER, "iat": int(now())},
                      SIGNING_KEY, algorithm="EdDSA",
                      headers={"typ": "u4a-verdict+jwt", "kid": KID})


def tally_claims(jws: str, issuer: str) -> dict:
    """A request from a tally, verified against the keys it publishes.

    Same shape as `/org/notice` and for the same reason: the alternative is a
    shared secret, and a shared secret between one owner's authority and a
    coordinator that several owners use is a secret that authenticates the
    wrong set of people.
    """
    # Twice: once against what is cached, and once against a fresh fetch if
    # that fails. A key the other party has rotated is indistinguishable from
    # a forgery when all you have is a stale copy of its JWKS, and the two
    # deserve very different answers.
    for fresh in (False, True):
        for jwk_dict in issuer_keys(issuer, fresh=fresh):
            try:
                # `exp` is enforced by being present — a tally signs its
                # questions short-lived so a captured one cannot be replayed
                # at an owner weeks later, under a policy she has since
                # changed.
                return jwt.decode(jws, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                  algorithms=["EdDSA"], issuer=issuer,
                                  options={"verify_aud": False,
                                           "require": ["exp", "iss"]})
            except jwt.InvalidTokenError:
                continue
    raise HTTPException(status_code=401,
                        detail="not signed by the tally named in this mandate")


async def tally_request(request: Request) -> tuple[str, dict, dict]:
    """(owner, record, claims) for a signed request from a tally.

    The order matters. The issuer is read from the *unverified* token only to
    find which mandate this is about, then the record says which tally that
    mandate names, and the signature is checked against that one. Reading the
    issuer to decide where to look is safe; reading it to decide anything
    else is not.
    """
    # Unauthenticated by construction — anyone can post here and the
    # signature is what settles it — so malformed input has to be a refusal
    # rather than a traceback.
    try:
        body = await request.json()
        token = (body or {}).get("request") or ""
        unverified = jwt.decode(token, options={"verify_signature": False})
    except (ValueError, jwt.InvalidTokenError):
        raise HTTPException(status_code=400, detail="that is not a tally request")
    owner = unverified.get("owner") or ""
    account = unverified.get("account") or ""
    if not serves(owner):
        raise HTTPException(status_code=404, detail="not an owner here")
    record = await st(owner).mandate(account)
    if record is None:
        raise HTTPException(status_code=403,
                            detail="this owner is not a party to that mandate")
    claims = tally_claims(token, record["tally"])
    if claims.get("owner") != owner or claims.get("account") != account:
        raise HTTPException(status_code=401, detail="that request is about somebody else")
    return owner, record, claims


async def joint_tier(owner: str, resource_id: str) -> tuple[str | None, dict]:
    return policy.tier_for_resource(await st(owner).tiers(), resource_id)


@app.post("/joint/quote")
async def joint_quote(request: Request) -> dict:
    """This owner's terms over a jointly held resource.

    Quoted so that the tally can fold every holder's terms into the one
    document an agent signs. A holder who has written nothing over the
    resource quotes nothing, which under a unanimity rule stops the request:
    silence is not consent, and an owner who has not said what she permits
    has not permitted anything.
    """
    owner, record, claims = await tally_request(request)
    resources = (record["mandate"].get("resources") or [])
    tier_id, tier = await joint_tier(owner, claims.get("resource_id") or "")
    event("joint.quoted", owner=owner, account=record["account"],
          resource_id=claims.get("resource_id"), tier=tier_id)
    if tier_id is None:
        return {"owner": owner, "tier": None,
                "because": "this holder has written no terms over this resource"}
    return {"owner": owner, "tier_id": tier_id,
            "tier": joint.quote_of(tier, resources)}


@app.post("/joint/verdict")
async def joint_verdict(request: Request) -> dict:
    """This owner's answer about one negotiation over a jointly held resource.

    Either a signed verdict or `pending`. Pending is not a failure and not a
    timeout: it is a person being asked, and the tally holds the agent's
    ticket while she is asked exactly as a single authority would.
    """
    owner, record, claims = await tally_request(request)
    account, negotiation = record["account"], claims.get("negotiation") or ""
    resource_id = claims.get("resource_id") or ""
    mandate = record["mandate"]

    def refuse(*because: str) -> dict:
        return {"verdict": joint_verdict_jws({
            "holder": owner, "account": account, "negotiation": negotiation,
            "resource_id": resource_id, "contract": claims.get("contract"),
            "effect": "refuse", "because": list(because),
            "exp": int(now()) + 300})}

    if not joint.claims_match(resource_id, mandate.get("resources") or []):
        return refuse("that resource is not part of this mandate")

    # She may already have answered. Read before anything is re-evaluated:
    # the tally polls, and a question she has decided must not be re-asked or
    # re-judged against a policy she has edited in the meantime.
    pended = await st(owner).negotiation(negotiation)
    if pended is not None and pended.get("decision") in ("approved", "denied"):
        await close_negotiation(pended)
        if pended["decision"] == "denied":
            event("joint.verdict", owner=owner, negotiation=negotiation,
                  effect="refuse", why="owner-denied")
            return refuse("this holder declined")
        event("joint.verdict", owner=owner, negotiation=negotiation,
              effect="allow", why="owner-approved")
        await ledger_add(owner, "joint_allowed", negotiation,
                         {"account": account, "resource_id": resource_id},
                         handle=pended.get("handle"))
        return {"verdict": joint_verdict_jws({
            "holder": owner, "account": account, "negotiation": negotiation,
            "resource_id": resource_id, "contract": claims.get("contract"),
            "effect": "allow", "exp": int(now()) + 300})}
    if pended is not None:
        return {"pending": True, "family": negotiation}

    tier_id, tier = await joint_tier(owner, resource_id)
    if tier_id is None:
        return refuse("this holder has written no terms over this resource")

    # The agent's own signature, verified here rather than relayed. The
    # audience is the tally, because the tally is who the agent negotiated
    # with — and this is the point at which a tally that folded dishonestly
    # is caught, because what comes out is compared against her terms below.
    agreement = claims.get("agreement") or ""
    try:
        contract, signer_jwk, identity = contract_identity(
            agreement, record["tally"])
    except Exception as exc:                                    # noqa: BLE001
        return refuse(f"the agreement did not verify: {exc}")
    if s256(base64.urlsafe_b64decode(
            agreement + "=" * (-len(agreement) % 4))) != claims.get("contract"):
        return refuse("the agreement does not match the digest it was sent under")

    if problems := joint.verdict_problems(contract, tier, resource_id):
        event("joint.fold_rejected", owner=owner, negotiation=negotiation,
              because=problems)
        await ledger_add(owner, "joint_refused", negotiation,
                         {"account": account, "because": problems})
        return refuse(*problems)

    handle = connection_handle(identity, signer_jwk)
    conn = await st(owner).connection(handle)
    if origin := operator_origin(identity):
        if origin in await st(owner).blocked_operators():
            return refuse("this holder does not accept agents from that operator")
    axes = assurance.assess(identity)
    facts = {
        "assurance": axes,
        "standing": standing_facts(
            conn, tier_id, await trajectory_facts(owner, handle),
            await first_party_fact(owner, identity, axes)),
        "request": {"expires_in": contract.get("expires_in", 0),
                    "max_expires_in": tier["terms"]["expires_in"],
                    "reason": contract.get("reason"),
                    "mission": contract.get("mission")},
        "tier": tier_id,
    }
    requirement, reasons = policy.evaluate(tier, facts)
    if requirement == policy.REFUSE:
        await ledger_add(owner, "joint_refused", negotiation,
                         {"account": account, "because": reasons}, handle=handle)
        return refuse(*(reasons or ["this holder's terms refuse it"]))

    needs_connection = conn is None or conn["status"] != "active"
    if needs_connection or requirement == policy.ASK:
        # Her decision, in her own portal, alongside every other request
        # waiting on her. A joint resource does not get its own queue: the
        # question "may this agent do this" is the same question, and the
        # only thing different about it is who else is being asked.
        rec = {
            "family": negotiation,
            "owner": owner,
            "state": "awaiting-owner",
            "decision": None,
            # Every negotiation this store holds carries one, and a joint one
            # has to as well: the reaper reads it across all of them, so a
            # record without it does not merely fail to expire — it takes the
            # whole grant loop down on the next sweep. It also means a
            # question no holder ever answers stops waiting, which is the
            # behaviour the rest of the queue already has.
            "expires": time.time() + PENDING_TTL,
            "pending_kind": "joint",
            "tier": tier_id,
            "resource_id": resource_id,
            "resource_scopes": list(contract.get("scope") or []),
            "handle": handle,
            "contract": {**contract, "_identity": identity},
            "template": {"enforced": {}},
            "assurance": axes,
            "assurance_notes": assurance.describe(axes, identity),
            "because": reasons,
            "joint": {"account": account, "tally": record["tally"],
                      "holders": [h["owner"] for h in mandate.get("holders") or []],
                      "rule": (mandate.get("rule") or {}).get("kind")},
        }
        await st(owner).save_negotiation(rec)
        event("joint.pending", owner=owner, negotiation=negotiation,
              account=account, tier=tier_id)
        await owner_notify(owner, {
            "type": "pending", "kind": "joint", "family": negotiation,
            "tier": tier_id, "tier_name": tier["name"],
            "purpose": contract.get("purpose"),
            "operation": contract.get("operation"),
            "reason": contract.get("reason"), "mission": contract.get("mission"),
            "prohibited": contract.get("prohibited"), "enforced": {},
            "identity": identity, "handle": handle, "assurance": axes,
            "assurance_notes": assurance.describe(axes, identity),
            "because": reasons, "joint": rec["joint"]})
        return {"pending": True, "family": negotiation}

    await st(owner).touch_connection(handle, utcstamp())
    event("joint.verdict", owner=owner, negotiation=negotiation, effect="allow",
          why="auto")
    await ledger_add(owner, "joint_allowed", negotiation,
                     {"account": account, "resource_id": resource_id},
                     handle=handle)
    return {"verdict": joint_verdict_jws({
        "holder": owner, "account": account, "negotiation": negotiation,
        "resource_id": resource_id, "contract": claims.get("contract"),
        "effect": "allow", "exp": int(now()) + 300})}


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    # Read before parsing. A resource server with no shared secret
    # authenticates by signing this request, and the signature covers a
    # digest of the body — so the exact bytes have to be kept. Declaring the
    # fields as FastAPI form parameters would drain the stream before the
    # handler ran, which is why they are pulled out by hand here.
    body = await request.body()
    form = await request.form()
    grant_type = form.get("grant_type") or ""
    ticket = form.get("ticket")
    claim_token = form.get("claim_token")
    claim_token_format = form.get("claim_token_format")
    decline = form.get("decline")
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    scope = form.get("scope")
    owner = form.get("owner")
    # PAT issuance: a resource server the owner has authorized exchanges its
    # client credentials for a uma_protection-scoped token (FedAuthz's PAT).
    if grant_type == "client_credentials":
        # A resource server holds one PAT per owner it serves, so the request
        # has to say which. Defaulted rather than required, because a
        # single-owner deployment has nothing to disambiguate.
        pat_owner = owner or DEFAULT_OWNER
        if not serves(pat_owner):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        await st(pat_owner).seed()
        rs = await st(pat_owner).resource_server(client_id or "")
        if rs is None:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        # Two ways to be this resource server, and which one applies is a
        # property of the record rather than of the request — so a client
        # that registered by signature cannot fall back to guessing a secret,
        # and one holding a secret cannot be impersonated by anyone who can
        # publish a key. The empty-secret case is branched on explicitly:
        # compare_digest("", "") is true, and a record with no secret must
        # never be openable by sending none.
        if rs.get("secret"):
            if not secrets.compare_digest(client_secret or "", rs["secret"]):
                return JSONResponse({"error": "invalid_client"}, status_code=401)
        elif not await verify_resource_server_signature(
                request, body, rs.get("resource_uri") or ""):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        if rs["status"] == "pending":
            # Registered, not yet hers. The distinct code is what tells the
            # resource server to wait rather than to register again.
            return JSONResponse(
                {"error": "authorization_pending",
                 "error_description": "the owner has not yet authorized this "
                                      "resource server"},
                status_code=403)
        if rs["status"] != "active":
            return JSONResponse(
                {"error": "access_denied",
                 "error_description": "the owner has revoked this resource server"},
                status_code=403)
        if scope != "uma_protection":
            return JSONResponse({"error": "invalid_scope"}, status_code=400)
        return JSONResponse(await issue_pat(pat_owner, client_id))

    if grant_type != "urn:ietf:params:oauth:grant-type:uma-ticket":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    ticket_owner, raw_ticket = split_ticket(ticket)
    ticket_owner = ticket_owner or DEFAULT_OWNER
    await st(ticket_owner).reap_expired()
    rec = await st(ticket_owner).consume_ticket(raw_ticket)
    if rec is None:
        event("ticket.presented", corr=None, result="invalid_grant")
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    family = rec["family"]
    event("ticket.presented", corr=family, state=rec["state"])

    # The requesting side declines the proffered terms. Refusals are records
    # too (IEEE 7012 5.2.4): the owner's ledger notes who walked away from
    # which terms, and the negotiation ends.
    if decline == "true" and rec["state"] == "need_info":
        event("terms.declined", corr=family, tier=rec.get("tier"),
              template_id=rec.get("template", {}).get("template_id"))
        # The one entry with no agent to name, and it is a property of the
        # protocol rather than a gap here: a decline arrives at beat 2, before
        # the requesting side has signed anything, so there is no key, no
        # identity and nothing to file it under. Her record says her terms were
        # refused, which is true and is all that is knowable.
        await ledger_add(rec["owner"], "refused", family, {
            "tier": rec.get("tier"),
            "terms_uri": rec.get("template", {}).get("terms_uri"),
        })
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Pending ask-me ticket being re-presented (beat 3, taking longer).
    if rec["state"] == "awaiting-owner":
        return await pending_poll(rec)

    # Before her policy is read at all. If an organization claims this
    # resource and its ceiling cannot be established, nothing proceeds — the
    # resource is the organization's, and a request that slipped through
    # while its authority was unreachable is exactly the access the charter
    # exists to prevent. This call is also where a charter that moved gets
    # applied, so the tier read on the next line is already inside it.
    if blocked := await organization_blocks(rec["owner"], rec["resource_id"]):
        event("policy.evaluated", corr=family, result="org-unreadable")
        await ledger_add(rec["owner"], "org_refused", family,
                         {"because": [blocked]})
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied",
                             "error_description": blocked}, status_code=403)

    tier_id, tier = policy.tier_for_resource(await st(rec["owner"]).tiers(),
                                             rec["resource_id"])
    if tier_id is None:
        event("policy.evaluated", corr=family, result="no-tier")
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Beat 1a: an organization that federates identity wants to know whose
    # agent this is before anybody's terms are read.
    #
    # Only for its own resources, and only when its charter names a provider.
    # Everything else on this server — her own accounts, anything she holds
    # jointly — never reaches this branch, and no enterprise provider is
    # consulted about any of it.
    idp = federated_provider(await org_envelope(rec["owner"]), rec["resource_id"])
    if idp and not rec.get("asserted"):
        if claim_token_format == ID_JAG_FORMAT and claim_token:
            try:
                asserted = verify_id_jag(claim_token, idp, rec["owner"],
                                         rec["resource_id"])
            except ValueError as exc:
                event("identity.rejected", corr=family, reason=str(exc))
                await ledger_add(rec["owner"], "identity_refused", family,
                                 {"because": [str(exc)]})
                await close_negotiation(rec)
                return JSONResponse(
                    {"error": "request_denied", "error_description": str(exc)},
                    status_code=403)
            rec["asserted"] = {
                "issuer": asserted["iss"],
                "subject": asserted.get("sub"),
                "member": asserted.get("preferred_username"),
                "application": asserted.get("client_id"),
                "scope": (asserted.get("scope") or "").split(),
                "jti": asserted.get("jti"),
            }
            event("identity.asserted", corr=family, provider=asserted["iss"],
                  member=rec["asserted"]["member"],
                  application=rec["asserted"]["application"])
            # Established. Her terms are the next question, and they are hers.
            return await need_info_response(rec, tier_id, tier)
        return await need_identity_response(rec, idp)

    # Beat 2: no contract yet -> dictate Alice's terms.
    if not claim_token:
        return await need_info_response(rec, tier_id, tier)

    # Beat 3: contract committed.
    if claim_token_format != AGREEMENT_FORMAT:
        return JSONResponse({"error": "invalid_claim_token_format"}, status_code=400)
    if rec["state"] != "need_info":
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    try:
        contract, signer_jwk = verify_contract(claim_token, rec)
    except Exception as exc:
        event("contract.rejected", corr=family, reason=str(exc))
        await close_negotiation(rec)
        return JSONResponse(
            {"error": "request_denied", "error_description": str(exc)}, status_code=403
        )

    raw = base64.urlsafe_b64decode(claim_token + "=" * (-len(claim_token) % 4))
    contract_hash = s256(raw)
    rec["contract"] = contract
    rec["contract_hash"] = contract_hash
    rec["agreement_jws"] = raw.decode()
    rec["signer_jwk"] = signer_jwk
    if contract["_identity"].get("sub"):
        rec["agent_sub"] = contract["_identity"]["sub"]
    event("contract.committed", corr=family, tier=rec["tier"],
          contract=contract_hash, identity=contract["_identity"]["level"])

    # Named before the first ledger write rather than after it. The promise is
    # the first entry that has an agent to attribute, and both inputs have been
    # in hand since verify_contract returned.
    handle = connection_handle(contract["_identity"], signer_jwk)

    await ledger_add(rec["owner"], "promised", family, {
        "tier": rec["tier"],
        "purpose": contract["purpose"],
        "prohibited": contract["prohibited"],
        "expires_in": contract["expires_in"],
        "contract": contract_hash,
        "terms_uri": contract["terms_uri"],
        "operation": contract.get("operation"),
        "reason": contract.get("reason"),
        "mission": contract.get("mission"),
    }, handle=handle)

    # Day-1 handshake: an agent without a standing connection pends — the same
    # request_submitted machinery, asking a different question ("do you want a
    # relationship with this agent?"). Alice's approval creates the connection
    # AND releases this negotiation in one tap.
    conn = await st(rec["owner"]).connection(handle)
    needs_connection = conn is None or conn["status"] != "active"

    # What her authority can establish about this agent, and what she has
    # herself seen of it. Kept apart on purpose — see `assurance.py`.
    # An operator she has shut out. Blocking is a *restriction*, so it can rest
    # on what the agent claims about itself without any of the usual worry: an
    # agent that lies about its operator only ever lies itself into a refusal.
    #
    # What blocking does not do is remove them from the internet. Drop the
    # client_id and the same party is back as an anonymous stranger — with no
    # accountability, in the small lane, pending in front of her like any
    # other. That is the honest limit, and it is why the lane split matters
    # more than the block does.
    origin = operator_origin(contract["_identity"])
    if origin and origin in await st(rec["owner"]).blocked_operators():
        event("policy.evaluated", corr=family, result="operator-blocked",
              operator=origin)
        await ledger_add(rec["owner"], "refused", family, {"tier": rec["tier"],
                                             "operator": origin,
                                             "because": ["operator is blocked"]},
                         handle=handle)
        await close_negotiation(rec)
        return JSONResponse(
            {"error": "request_denied",
             "error_description": f"the owner does not accept agents from {origin}"},
            status_code=403)

    # The organization has shut this agent out of *its* resources. Checked
    # here, beside her own operator block, and scoped the way that one is
    # not: it bites only on the resources the charter claims, so an agent an
    # administrator turned away from the firm's book goes on reading her own
    # portfolio for her exactly as before.
    if await org_blocks_agent(rec["owner"], handle, contract["_identity"]):
        envelope, _ = await org_scope(rec["owner"])
        if org.reaches(rec["resource_id"], envelope):
            event("policy.evaluated", corr=family, result="org-blocked",
                  tier=rec["tier"])
            await ledger_add(rec["owner"], "org_refused", family, {
                "tier": rec["tier"],
                "because": ["your organization has shut this agent out of its "
                            "resources"]}, handle=handle)
            await close_negotiation(rec)
            return JSONResponse(
                {"error": "request_denied",
                 "error_description": "the resource owner's organization has "
                                      "withdrawn this agent's access to its "
                                      "resources"}, status_code=403)

    axes = assurance.assess(contract["_identity"])
    facts = {
        "assurance": axes,
        "standing": standing_facts(
            conn, rec["tier"], await trajectory_facts(rec["owner"], handle),
            await first_party_fact(rec["owner"], contract["_identity"], axes)),
        "request": {"expires_in": contract.get("expires_in", 0),
                    "max_expires_in": tier["terms"]["expires_in"],
                    "reason": contract.get("reason"),
                    "mission": contract.get("mission")},
        "tier": rec["tier"],
    }
    requirement, reasons = policy.evaluate(tier, facts)
    event("assurance.assessed", corr=family, **axes)

    # Both layers must allow, and either may refuse. That is the whole
    # composition rule, and the code is the sentence: the organization's
    # answer can raise the requirement or end the negotiation, and there is
    # no branch in which it lowers one.
    verdict = await organization_verdict(rec, tier, facts)
    rec["org"] = verdict or None
    if verdict.get("effect") == policy.REFUSE:
        event("policy.evaluated", corr=family, result="org-refused",
              tier=rec["tier"], org=verdict.get("org"))
        await ledger_add(rec["owner"], "org_refused", family, {
            "tier": rec["tier"],
            "organization": verdict.get("organization"),
            "charter_version": verdict.get("charter_version"),
            "because": verdict.get("because") or [],
        }, handle=handle)
        await close_negotiation(rec)
        return JSONResponse(
            {"error": "request_denied",
             "error_description": "; ".join(verdict.get("because") or [
                 "the resource owner's organization refused this request"])},
            status_code=403)
    if verdict.get("effect") == policy.ASK and requirement == policy.AUTO:
        # She is asked because her employer requires it, and the dialog says
        # so in the organization's own words rather than folding them in
        # among her rules — she should be able to tell which of the two
        # layers is the reason she is being interrupted.
        requirement = policy.ASK

    if requirement == policy.REFUSE:
        event("policy.evaluated", corr=family, result="refused", tier=rec["tier"],
              because=reasons)
        await ledger_add(rec["owner"], "refused", family, {"tier": rec["tier"],
                                             "because": reasons},
                         handle=handle)
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied",
                             "error_description": "; ".join(reasons)},
                            status_code=403)

    needs_operation_approval = requirement == policy.ASK

    # Her attention has a depth limit, and only strangers spend it. An agent she
    # already has standing with is never counted at all.
    #
    # Strangers are counted per *lane*, and that split is the whole point: Bob's
    # agent is a stranger too on first contact, so a single queue let a flood of
    # anonymous bots keep him out of the relationship he needed to form. An
    # agent whose named operator published its key queues against other
    # attributable agents only, where a flood has somebody's name on it. See
    # policy.py.
    if needs_connection:
        lane = policy.pend_lane(axes)
        budget = policy.pend_budget(lane)
        waiting = sum(
            1 for p in await st(rec["owner"]).pending_negotiations()
            if p.get("pending_kind") == "connection" and p["family"] != family
            and policy.pend_lane(p.get("assurance") or {}) == lane)
        if waiting >= budget:
            event("policy.evaluated", corr=family, result="attention-budget",
                  lane=lane, waiting=waiting, budget=budget)
            await close_negotiation(rec)
            return JSONResponse(
                {"error": "request_denied",
                 "error_description": "the owner is not accepting new agent "
                                      "requests at the moment; try later"},
                status_code=429)

    if needs_connection or needs_operation_approval:
        kind = "connection" if needs_connection else "operation"
        rec["state"] = "awaiting-owner"
        rec["decision"] = None
        rec["pending_kind"] = kind
        rec["handle"] = handle
        # Persisted on the negotiation, not only pushed over SSE: her portal
        # lists pending requests with a plain GET after a reload, and a dialog
        # that shows what was checked only to whoever was watching live is not
        # much of a dialog.
        rec["assurance"] = axes
        rec["assurance_notes"] = assurance.describe(axes, contract["_identity"])
        rec["because"] = reasons
        rotated = await new_ticket(rec)
        event("ticket.awaiting_owner", corr=family, tier=rec["tier"], kind=kind)
        await owner_notify(
            rec["owner"],
            {
                "type": "pending",
                "kind": kind,
                "family": family,
                "tier": rec["tier"],
                "tier_name": tier["name"],
                "purpose": contract["purpose"],
                "operation": contract.get("operation"),
                "reason": contract.get("reason"),
                "mission": contract.get("mission"),
                "prohibited": contract["prohibited"],
                "enforced": rec["template"].get("enforced") or {},
                "identity": contract["_identity"],
                "handle": handle,
                # What her authority could and could not establish, in
                # sentences rather than integers. A dialog that shows a level
                # without saying what was checked teaches nothing.
                "assurance": axes,
                "assurance_notes": assurance.describe(axes, contract["_identity"]),
                "because": reasons,
                "organization": rec.get("org") or None,
            }
        )
        event("owner.notified", corr=family, kind=kind)
        return JSONResponse(
            {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
            status_code=403,
        )

    await st(rec["owner"]).touch_connection(handle, utcstamp())
    await st(rec["owner"]).note_tier_grant(handle, rec["tier"])
    event("policy.evaluated", corr=family, result="auto-grant", tier=rec["tier"],
          connection=handle, because=reasons or None)
    if reasons and requirement == policy.AUTO and tier.get("ask_me"):
        # A rule she wrote lowered an ask-me tier to automatic. That is the
        # one direction worth being able to audit after the fact, so it is a
        # ledger entry and not only a log line.
        await ledger_add(rec["owner"], "relaxed", family, {"tier": rec["tier"],
                                             "because": reasons},
                         handle=handle)
    # The operation, when the contract carries one — not None.
    #
    # This path used to hardcode None, and it was unreachable while every
    # per-operation tier was ask-me with no rule that could lower it. A
    # relaxation reaches it: the tier still requires a named act at commit,
    # `verify_contract` still refuses a contract without one, and the
    # enforcement point still checks the digest on the call. Issuing an
    # unbound token here would have made the grant useless rather than
    # dangerous — the PEP refuses it with `operation_mismatch` — but a tier
    # that silently stops working when she relaxes it is its own kind of
    # broken.
    granted = await issue_rpt(rec, contract_hash, signer_jwk,
                              contract.get("operation"))
    await close_negotiation(rec)
    return JSONResponse(granted)


async def pending_poll(rec: dict) -> JSONResponse:
    family = rec["family"]
    if rec.get("decision") == "approved":
        if rec.get("pending_kind") == "connection":
            handle = rec["handle"]
            identity = rec["contract"]["_identity"]
            # A previously revoked agent that she admits again starts a new
            # relationship, but not a clean record: `standing.never_revoked`
            # would be worthless if a revocation could be cleared by asking a
            # second time.
            prior = await st(rec["owner"]).connection(handle) or {}
            await st(rec["owner"]).put_connection({
                "handle": handle,
                "identity": identity,
                "label": identity.get("sub") or f"Agent {handle[4:12]}",
                "status": "active",
                "first_seen": utcstamp(),
                "last_access": None,
                # Which tiers this connection has actually been granted at.
                # Being admitted is not the same as being admitted everywhere:
                # `standing.first_at_tier` reads this, so the first request at
                # each new tier comes back to her.
                "tiers_granted": [],
                # Tiers she personally said yes at. Kept separate from the
                # line above because only this one may ever relax a rule.
                "tiers_approved": [],
                "revocations": int(prior.get("revocations", 0)),
            })
            event("connection.approved", corr=family, handle=handle)
            await ledger_add(rec["owner"], "connected", family, {"identity": identity},
                             handle=handle)
        event("policy.evaluated", corr=family, result="owner-approved", tier=rec["tier"])
        # Tier policy still applies after connection: an ask-me tier needs its
        # per-operation approval, which Alice's single tap covered only if this
        # negotiation carried the operation (it did — the contract binds it).
        if handle := rec.get("handle"):
            await st(rec["owner"]).note_tier_grant(handle, rec["tier"])
            # Only when she answered it herself. That is the only kind of fact
            # a relaxation is allowed to rest on, and an administrator at her
            # organization answering on her behalf is emphatically not it —
            # see `decide_pending`.
            if not rec.get("decided_by"):
                await st(rec["owner"]).note_tier_approval(handle, rec["tier"])
            else:
                event("policy.evaluated", corr=family, result="decided-by-org",
                      tier=rec["tier"], by=rec["decided_by"].get("admin"))
        granted = await issue_rpt(rec, rec["contract_hash"], rec["signer_jwk"],
                                  rec["contract"].get("operation"))
        await close_negotiation(rec)
        return JSONResponse(granted)
    if rec.get("decision") == "denied":
        event("policy.evaluated", corr=family, result="owner-denied", tier=rec["tier"])
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)
    rotated = await new_ticket(rec)  # still pending: rotate and keep waiting
    return JSONResponse(
        {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
        status_code=403,
    )


# --- Owner API (the portal's backend) ----------------------------------------


@app.get("/owner/pending")
async def owner_pending(request: Request) -> list:
    owner = await require_owner(request)
    return await pending_view(owner)


async def pending_view(owner: str) -> list:
    """Everything waiting on a decision, for whoever is entitled to make it.

    Read by the owner's portal, and by an administrator of the organization
    she administers these resources for. The same list either way: an
    administrator who saw a different set of pending requests from the person
    they are co-administering with would be looking at a different system.
    """
    return [
        {
            "family": rec["family"],
            "kind": rec.get("pending_kind", "operation"),
            "tier": rec["tier"],
            "purpose": rec["contract"]["purpose"],
            "operation": rec["contract"].get("operation"),
            "reason": rec["contract"].get("reason"),
            "mission": rec["contract"].get("mission"),
            "prohibited": rec["contract"]["prohibited"],
            "enforced": rec.get("template", {}).get("enforced") or {},
            "identity": rec["contract"]["_identity"],
            "handle": rec.get("handle"),
            "assurance": rec.get("assurance", {}),
            "assurance_notes": rec.get("assurance_notes", []),
            "because": rec.get("because", []),
            "organization": rec.get("org") or None,
            # Which resource, so an administrator can see at a glance whether
            # this is one his organization governs — and so the surface can
            # say why he may not approve one that is not.
            "resource_id": rec.get("resource_id"),
        }
        for rec in await st(owner).pending_negotiations()
    ]


@app.post("/owner/pending/{family}/decision")
async def owner_decision(family: str, request: Request) -> dict:
    owner = await require_owner(request)
    body = await request.json()
    return await decide_pending(owner, family, body.get("decision"), actor=None)


async def decide_pending(owner: str, family: str, decision: str,
                         actor: dict | None) -> dict:
    """One pending request, answered. By her, or by an administrator of the
    organization she administers these resources for.

    `actor` is None when it is her own tap, and names the organization and
    the person when it is not. It changes nothing about what happens and
    everything about what is written down: a decision she did not make must
    never appear in her record as one she did.
    """
    if decision not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="decision must be approved|denied")
    # The store's guard, not a read-then-write here: a double tap, or two
    # portals open on the same request, must produce one decision. It is also
    # what makes co-administration safe: she and an administrator answering
    # the same request at the same moment produce one answer, not two.
    if not await st(owner).decide(family, decision):
        raise HTTPException(status_code=404, detail="no pending negotiation for that family")
    event("owner.decision", corr=family, decision=decision,
          by=(actor or {}).get("admin") or owner)
    # Read after the decision, not before: `decide` is the guard, and doing the
    # lookup first would invite someone to move the guard behind it. The
    # negotiation survives its own decision — `close_negotiation` runs when the
    # grant is issued — so the handle it was pending under is still there.
    pended = await st(owner).negotiation(family)
    if pended is not None and actor:
        # Who decided, on the record the grant loop will read back.
        #
        # This is not bookkeeping. `standing.approved_at_tier` is one of the
        # few facts allowed to *relax* one of her rules, and it exists because
        # "she personally approved something here" is a decision of hers. An
        # administrator's approval must never become that fact: it would let
        # somebody else's decision, taken once, loosen her policy for every
        # request afterwards. So the actor is persisted here and read in
        # `pending_poll`, which is the only place that records the approval.
        pended["decided_by"] = actor
        await st(owner).save_negotiation(pended)
    # Record both outcomes: "what did I decide" is an audit question, and a
    # denial is as much a decision as an approval.
    await ledger_add(owner, "approved" if decision == "approved" else "denied", family,
                     {"decision": decision, "tier": (pended or {}).get("tier"),
                      **({"by": actor} if actor else {})},
                     handle=(pended or {}).get("handle"))
    await owner_notify(owner, {"type": "decided", "family": family,
                               "decision": decision,
                               "by": actor})
    return {"family": family, "decision": decision, "by": actor}


@app.get("/owner/resource-servers")
async def owner_resource_servers(request: Request) -> list:
    """The resource servers Alice has authorized to use her Protection API —
    the other standing relationship her AS holds, beside agent connections."""
    owner = await require_owner(request)
    return [
        {"client_id": cid, **{k: v for k, v in rs.items() if k != "secret"}}
        for cid, rs in (await st(owner).resource_servers()).items()
    ]


@app.post("/rs/register")
async def rs_register(request: Request) -> JSONResponse:
    """A resource server introduces itself to an owner's authority.

    It arrives holding nothing this server issued. What it presents is a
    signature over the request, made with a key published at the origin of
    the resource it claims to serve — so the credential is the origin, and
    verifying it is a fetch this server performs rather than a claim it is
    handed.

    Success is 202, not 200. A verified signature establishes *who is asking*
    and nothing else; the answer is hers, and until she gives it the record
    sits in her resource-server registry marked pending and opens no door. A
    resource server she has revoked may ask again — and lands in the same
    pending state, because a second request is not a reversal of her first
    decision.
    """
    body = await request.body()
    try:
        req = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    owner = (req.get("owner") or DEFAULT_OWNER).strip()
    if not serves(owner):
        return JSONResponse(
            {"error": "invalid_request",
             "error_description": "this authorization server serves a different owner"},
            status_code=403)
    # An owner exists because a person set one up. A resource server naming a
    # string must not be able to bring one into being, complete with default
    # policy and terms — on a single-owner server `serves` already settles it,
    # but on one holding many this is the check that does. Before the fetch
    # below, so an unknown owner costs no outbound request either.
    if SERVED_OWNER is None and owner not in await STORE.owners():
        return JSONResponse(
            {"error": "invalid_request",
             "error_description": "no such owner at this authorization server"},
            status_code=403)

    resource_uri = (req.get("resource_uri") or "").strip()
    if not await verify_resource_server_signature(request, body, resource_uri):
        event("resource_server.registration_refused", owner=owner,
              resource_uri=resource_uri,
              reason="no signature from a key published at that origin")
        return JSONResponse(
            {"error": "invalid_client",
             "error_description":
                 "register by signing with a key published at the origin of "
                 "the resource you claim to serve"},
            status_code=401)

    client_id = _origin_of(resource_uri)
    await ensure_owner(owner)
    existing = await st(owner).resource_server(client_id)
    if existing and existing.get("status") == "active":
        # Already hers. Saying so beats re-pending a working relationship
        # every time the resource server restarts.
        return JSONResponse({"client_id": client_id, "status": "active"})

    await st(owner).put_resource_server(client_id, {
        "secret": "",
        # Stored raw and capped. This is the one field on the record the
        # registering side authors, so it is the one a surface rendering it
        # has to escape — see the portal's `esc`. Escaping it here would put
        # markup in the store, double-escape wherever that is done properly,
        # and let the cap cut an entity in half.
        "name": str(req.get("name") or client_id)[:120],
        "status": "pending",
        "consented": None,
        "last_pat_issued": (existing or {}).get("last_pat_issued"),
        "resource_uri": resource_uri,
        "registered": utcstamp(),
        # How it will authenticate from here on. Recorded because the two are
        # not interchangeable: a seeded relationship holds a shared secret,
        # and this one holds nothing at all.
        "auth": "origin_signature",
    })
    event("resource_server.registered", owner=owner, client_id=client_id,
          resource_uri=resource_uri, status="pending",
          previously=(existing or {}).get("status"))
    # Only on a change of state. A resource server she has withdrawn will keep
    # asking for as long as traffic keeps arriving for her, and each of those
    # is the same question she has already been asked.
    if (existing or {}).get("status") != "pending":
        await owner_notify(owner, {"type": "resource_server_pending",
                                   "client_id": client_id,
                                   "resource_uri": resource_uri})
    return JSONResponse(
        {"client_id": client_id, "status": "pending",
         "error": "authorization_pending",
         "error_description": "the owner has been asked"},
        status_code=202)


def _origin_of(url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


@app.post("/owner/resource-servers/decision")
async def owner_resource_server_decision(request: Request) -> dict:
    """Her answer about a resource server, in the same shape as her answer
    about an agent's first contact — because it is the same kind of question.

    The client_id is in the body rather than the path. It is an https URL for
    anything that registered itself, and a URL inside a path survives neither
    percent-decoding nor a proxy that normalises `//`.
    """
    owner = await require_owner(request)
    body = await request.json()
    client_id = (body.get("client_id") or "").strip()
    decision = body.get("decision")
    if decision == "approved":
        if not await st(owner).approve_resource_server(client_id, utcstamp()):
            raise HTTPException(
                status_code=404,
                detail="no pending registration for that resource server")
        status = "active"
    elif decision == "revoked":
        if not await st(owner).revoke_resource_server(client_id):
            raise HTTPException(status_code=404, detail="unknown resource server")
        status = "revoked"
    else:
        raise HTTPException(status_code=400,
                            detail="decision must be approved or revoked")
    event(f"resource_server.{decision}", client_id=client_id)
    await ledger_add(owner, "approved" if status == "active" else "revoked",
                     "-", {"resource_server": client_id})
    await owner_notify(owner, {"type": "resource_server_decided",
                               "client_id": client_id, "status": status})
    return {"client_id": client_id, "status": status}


@app.post("/owner/resource-servers/{client_id}/revoke")
async def owner_revoke_resource_server(client_id: str, request: Request) -> dict:
    owner = await require_owner(request)
    if not await st(owner).revoke_resource_server(client_id):
        raise HTTPException(status_code=404, detail="unknown resource server")
    event("resource_server.revoked", client_id=client_id)
    await ledger_add(owner, "revoked", "-", {"resource_server": client_id})
    return {"client_id": client_id, "status": "revoked"}


@app.get("/owner/operators")
async def owner_operators(request: Request) -> list:
    """Operators she has met, and whether she has shut any of them out.

    Assembled from her connections rather than kept as its own registry: an
    operator is not a thing she onboards, it is a name that turned up attached
    to agents she has already decided about.
    """
    owner = await require_owner(request)
    return await operators_view(owner)


async def operators_view(owner: str) -> list:
    blocked = await st(owner).blocked_operators()
    owned = await st(owner).owned_operators()
    seen: dict[str, dict] = {}
    for conn in await st(owner).connections():
        origin = operator_origin(conn.get("identity") or {})
        if origin is None:
            continue
        meta = (conn["identity"].get("client_metadata") or {})
        row = seen.setdefault(origin, {
            "origin": origin, "name": meta.get("client_name") or origin,
            "agents": 0, "active": 0, "blocked": origin in blocked,
            "blocked_at": (blocked.get(origin) or {}).get("blocked_at"),
            # Annotated on read rather than stored on the connection: she can
            # disclaim an origin at any moment, and a copy written when the
            # agent connected would go on saying it was hers.
            "mine": origin in owned,
            "claimed_at": (owned.get(origin) or {}).get("claimed_at"),
        })
        row["agents"] += 1
        row["active"] += 1 if conn.get("status") == "active" else 0
    for origin, rec in blocked.items():          # blocked before ever connecting
        seen.setdefault(origin, {"origin": origin, "name": origin, "agents": 0,
                                 "active": 0, "blocked": True,
                                 "blocked_at": rec.get("blocked_at"),
                                 "mine": origin in owned, "claimed_at": None})
    for origin, rec in owned.items():            # claimed before ever connecting
        row = seen.setdefault(origin, {"origin": origin, "name": origin,
                                       "agents": 0, "active": 0,
                                       "blocked": False, "blocked_at": None,
                                       "mine": True, "claimed_at": None})
        row["mine"] = True
        row["claimed_at"] = rec.get("claimed_at")
    return sorted(seen.values(), key=lambda r: r["origin"])


@app.post("/owner/operators/claim")
async def owner_claim_operator(request: Request) -> dict:
    """Say an origin is hers, so agents it vouches for are her own.

    The mirror of blocking, and deliberately not its equal. A block may rest on
    what an agent says about itself, because the worst a liar achieves is a
    refusal. This may not: it is the only thing in the profile that lets an
    agent meet *less* friction, so the claim alone is never enough. An agent is
    first-party only when this origin is claimed here **and** her authority
    found that agent's signing key in the operator's own key directory.

    Claiming an origin she does not control therefore buys nothing at all —
    she cannot publish keys there, so no agent of theirs can reach the second
    half. That is worth knowing before treating this as dangerous.
    """
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if not origin.startswith("https://"):
        raise HTTPException(status_code=400,
                            detail="an operator is named by its https origin")
    await st(owner).claim_operator(origin, utcstamp())
    event("operator.claimed", operator=origin)
    await ledger_add(owner, "claimed", "-", {"operator": origin})
    await owner_notify(owner, {"type": "decided", "family": "-", "decision": "claimed"})
    return {"origin": origin, "status": "mine"}


@app.post("/owner/operators/disclaim")
async def owner_disclaim_operator(request: Request) -> dict:
    """Stop treating an origin as hers.

    Takes effect on the next request rather than retroactively, and does not
    revoke anything. What the relaxation bought was fewer interruptions, not
    access she had not already granted, so there is nothing here to claw back —
    connections stay, grants stay, and the next negotiation simply faces the
    policy it would have faced anyway.
    """
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    dropped = await st(owner).disclaim_operator(origin)
    event("operator.disclaimed", operator=origin, was_claimed=dropped)
    if dropped:
        await ledger_add(owner, "disclaimed", "-", {"operator": origin})
    return {"origin": origin, "status": "not-mine", "was_claimed": dropped}


@app.post("/owner/operators/block")
async def owner_block_operator(request: Request) -> dict:
    """Shut out every agent of one operator, in one action.

    This is the reason the pend queue's second lane is keyed on an operator
    having *published this agent's key*: it makes a flood attributable, and an
    attributable flood is one she can answer here rather than one connection at
    a time.

    Blocking revokes what is already connected, in the same step. A block that
    stopped new requests and left live grants alone would leave her believing
    she had shut a door that was still open.
    """
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    return await block_operator_for(owner, origin, actor=None)


async def block_operator_for(owner: str, origin: str,
                             actor: dict | None) -> dict:
    if not origin.startswith("https://"):
        raise HTTPException(status_code=400,
                            detail="an operator is named by its https origin")
    await st(owner).block_operator(origin, utcstamp())
    revoked, tokens = 0, 0
    for conn in await st(owner).connections():
        if conn.get("status") != "active":
            continue
        if operator_origin(conn.get("identity") or {}) != origin:
            continue
        killed = await st(owner).revoke_connection(conn["handle"])
        if killed is not None:
            revoked, tokens = revoked + 1, tokens + killed
    event("operator.blocked", operator=origin, connections_revoked=revoked,
          rpts_deactivated=tokens, by=(actor or {}).get("admin") or owner)
    await ledger_add(owner, "revoked", "-", {"operator": origin,
                                      "connections_revoked": revoked,
                                      "rpts_deactivated": tokens,
                                      **({"by": actor} if actor else {})})
    await owner_notify(owner, {"type": "decided", "family": "-",
                               "decision": "revoked", "by": actor})
    return {"origin": origin, "connections_revoked": revoked,
            "rpts_deactivated": tokens}


@app.post("/owner/operators/unblock")
async def owner_unblock_operator(request: Request) -> dict:
    """Let them ask again. Deliberately not the reverse of blocking: the
    connections it revoked stay revoked, so unblocking restores the right to
    negotiate rather than the access that was withdrawn."""
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    return await unblock_operator_for(owner, origin, actor=None)


async def unblock_operator_for(owner: str, origin: str,
                               actor: dict | None) -> dict:
    if not await st(owner).unblock_operator(origin):
        raise HTTPException(status_code=404, detail="that operator is not blocked")
    event("operator.unblocked", operator=origin,
          by=(actor or {}).get("admin") or owner)
    if actor:
        # Unblocking is the one operator action that widens — it restores the
        # right to negotiate — so unlike a block it is written down even when
        # she does it herself would be noise, but never when somebody else
        # does it on her behalf.
        await ledger_add(owner, "org_acted", "-", {
            "what": "allowed an operator to ask again", "operator": origin,
            "by": actor})
        await owner_notify(owner, {"type": "decided", "family": "-",
                                   "decision": "unblocked", "by": actor})
    return {"origin": origin, "blocked": False}


@app.get("/owner/resources")
async def owner_resources(request: Request) -> list:
    """The owner's view of what her AS is protecting: every registered
    resource, joined with the tier whose policy governs it. This is the
    surface Alice attaches policy to before any agent has ever called."""
    owner = await require_owner(request)
    envelope = await org_envelope(owner) or {}
    # What an organization shares with her changes without this process being
    # told. `RESOURCES` is a per-process cache of what the resource server
    # publishes — deliberately, since it is re-pullable at any time — and the
    # events that change it happen elsewhere: an administrator sets a role at
    # the organization, the organization notifies *one* replica, and the
    # other two go on serving her a portal that is missing half of what she
    # can reach. Carol's single process never noticed; Alice's three did.
    #
    # So this listing re-reads what the resource server publishes. It is the
    # same repair `/perm` performs on an unknown id, with a second trigger:
    # `/perm` has a miss to react to, and the interesting cases here do not.
    # Two triggers, because one of them is always the wrong one on its own.
    # A resource that has just been shared with her has a grant matching
    # nothing in the registry, and she should not have to wait out a clock to
    # see it. A role that widened, or a membership that ended, leaves a set
    # that is merely short or merely long — nothing is missing to notice — so
    # those need the clock.
    granted = envelope.get("grants") or []
    absent = any(not any(org.claims_match(rid, [g]) for rid in RESOURCES)
                 for g in granted)
    if absent or _LAST_PULL.get(owner, 0) < time.time() - RESOURCE_REFRESH_S:
        await pull_registrations_now(owner)
    tiers = await st(owner).tiers()
    out = []
    for rid, desc in RESOURCES.items():
        tier_id, tier = policy.tier_for_resource(tiers, rid)
        # Whose resource this is. Hers unless an organization claims it, in
        # which case she administers it rather than owning it — and her
        # portal should say so, because the two are not the same thing and
        # the difference decides what happens when she leaves.
        shared = org.reaches(rid, envelope)
        out.append({
            "_id": rid,
            "name": desc.get("name") or rid,
            "type": desc.get("type"),
            "resource_scopes": desc["resource_scopes"],
            "tier": tier_id,
            "tier_name": tier["name"] if tier else None,
            "ask_me": tier["ask_me"] if tier else None,
            "registered_via": desc.get("registered_via", "push"),
            **({"shared_by": envelope.get("name"),
                "granted": org.claims_match(rid, envelope.get("grants") or []),
                "delegation": envelope.get("delegation")} if shared else {}),
        })
    return sorted(out, key=lambda r: r["_id"])


@app.get("/owner/policies")
async def owner_policies(request: Request) -> dict:
    owner = await require_owner(request)
    return await st(owner).tiers()


@app.get("/owner/policy-vocabulary")
async def owner_policy_vocabulary(request: Request) -> list:
    """The conditions her rules may use, and which of them may relax.

    Served so her portal can offer them as choices. One source of truth: a
    surface that hard-coded this list would eventually offer her something
    this server rejects.
    """
    await require_owner(request)
    return policy.vocabulary()


@app.post("/owner/policies")
async def owner_create_policy(request: Request) -> dict:
    """Alice writing a new tier: her terms, and which of her resources they
    govern.

    The resources have to be ones her authority already protects. That is not
    a limitation so much as the direction of the whole design — a resource
    server registers what it holds, and she attaches policy to it. She cannot
    write terms over something nobody is protecting.
    """
    owner = await require_owner(request)
    spec = await request.json()
    tier_id = (spec.get("id") or "").strip()
    try:
        tier = policy.new_tier(tier_id, spec, await st(owner).tiers(),
                               set(RESOURCES), await jointly_held(owner))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Terms she is writing for the first time are refused rather than
    # silently narrowed. The two directions are not symmetrical: an edit
    # clamped underneath her is the organization changing something, and
    # telling her about it afterwards is right; a *new* document quietly
    # altered between asking for it and getting it is her being told she
    # wrote something she did not.
    if envelope := await org_envelope(owner):
        if problems := org.would_exceed(spec, tier["resources"], envelope):
            raise HTTPException(status_code=400, detail="; ".join(problems))
    try:
        created = await st(owner).create_tier(tier_id, tier)
    except KeyError:
        raise HTTPException(status_code=409,
                            detail=f"there is already a tier called {tier_id!r}")
    event("policy.created", tier=tier_id, template_id=created["terms"]["template_id"],
          resources=created["resources"])
    await publish_terms(owner, tier_id, created)
    # The rest of the ceiling, applied rather than refused.
    #
    # `would_exceed` above refuses the two fields where she asked for
    # something wider than the organization allows — a longer expiry, a scope
    # it does not permit — because those are her intent and she should be
    # told. Mandatory prohibitions and always-ask are the other kind: she did
    # not ask for anything, the charter is adding to what she wrote, and
    # refusing a document over an addition would be pedantry.
    if envelope := await org_envelope(owner):
        patch, changes = org.patch_for(created, envelope)
        if patch is not None:
            created = await st(owner).update_tier(tier_id, patch)
            await publish_terms(owner, tier_id, created)
            event("org.clamped", owner=owner, tier=tier_id,
                  fields=[c["field"] for c in changes])
            created = {**created, "clamped": [c["text"] for c in changes]}
    return created


@app.delete("/owner/policies/{tier_id}")
async def owner_delete_policy(tier_id: str, request: Request) -> dict:
    """Remove a tier. Its resources become ungoverned, and an ungoverned
    resource is *denied* — so this withdraws access rather than widening it,
    which is the only safe direction for a destructive edit to fail in.

    Published terms are not deleted with it. An agreement signed against them
    stays checkable, which is the whole reason those documents are versioned
    and persistent.
    """
    owner = await require_owner(request)
    tiers = await st(owner).tiers()
    orphaned = list(tiers.get(tier_id, {}).get("resources") or [])
    if not await st(owner).delete_tier(tier_id):
        raise HTTPException(status_code=404, detail="unknown tier")
    event("policy.deleted", tier=tier_id, ungoverned=orphaned)
    return {"deleted": tier_id, "ungoverned": orphaned}


@app.put("/owner/policies/{tier_id}")
async def owner_update_policy(tier_id: str, request: Request) -> dict:
    owner = await require_owner(request)
    patch = await request.json()
    # The same rule the create path applies, because an edit can reach the
    # same shape: a tier that mixes a jointly held resource with anything
    # else is the way round the boundary that keeps an organization out of
    # what she holds with somebody else.
    if "resources" in patch:
        shared = await jointly_held(owner)
        asked = set(patch.get("resources") or [])
        if (mixed := shared & asked) and asked - shared:
            raise HTTPException(
                status_code=400,
                detail=f"{', '.join(sorted(mixed))} is held jointly, and terms "
                       f"over it cannot share a tier with anything else. Give "
                       f"it a tier of its own.")
    try:
        updated = await st(owner).update_tier(tier_id, patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown tier")
    except ValueError as exc:
        # A rule that could widen access on evidence the agent controls, or
        # one whose argument will not parse. Her editor shows this text, so it
        # has to say what is wrong rather than that something is.
        raise HTTPException(status_code=400, detail=str(exc))
    event("policy.updated", tier=tier_id, template_id=updated["terms"]["template_id"])
    # Publish the new version immediately so its terms URI dereferences from
    # the moment it exists; earlier versions remain served (persistent record).
    await publish_terms(owner, tier_id, updated)
    # Then the ceiling, if there is one. Clamping after rather than refusing
    # before: she edited terms that already existed, and the honest outcome
    # is the strictest reading of both documents plus a record saying which
    # of her fields the organization moved.
    if envelope := await org_envelope(owner):
        patch, changes = org.patch_for(updated, envelope)
        if patch is not None:
            updated = await st(owner).update_tier(tier_id, patch)
            await publish_terms(owner, tier_id, updated)
            event("org.clamped", owner=owner, tier=tier_id,
                  fields=[c["field"] for c in changes])
            await ledger_add(owner, "org_clamped", "-", {
                "tier": tier_id, "organization": envelope.get("name"),
                "charter_version": envelope.get("charter_version"),
                "changes": [c["text"] for c in changes]})
            updated = {**updated, "clamped": [c["text"] for c in changes]}
    return updated


@app.get("/owner/organization")
async def owner_organization(request: Request) -> dict:
    """Whether she administers these resources for anyone, and what that
    means for each of her tiers.

    Returned separately from `/owner/policies` on purpose. Her tiers are the
    document she edits — in a form or as JSON in the code editor — and mixing
    somebody else's ceiling into it would make her policy round-trip through
    her own editor carrying fields she cannot change.
    """
    owner = await require_owner(request)
    record = await org_record(owner)
    client = await org_client(owner) if record else None
    if client is None:
        # Not a member. The interesting thing to say is whether anyone has
        # asked her to be one — an invitation is a pending decision of hers,
        # and a surface that only told her about it if she went looking for
        # it would not be much of a notification.
        return {"enrolled": False,
                "enrolment_available": bool(ORG_ISSUER),
                "issuer": ORG_ISSUER,
                "invitation": await pending_invitation(owner)}
    envelope = await org_envelope(owner) or client.envelope
    tiers = await st(owner).tiers()
    return {
        "enrolled": True,
        "issuer": record["issuer"],
        "joined": record.get("joined"),
        "org": envelope.get("org"),
        "name": envelope.get("name"),
        "charter_version": envelope.get("charter_version"),
        "summary": envelope.get("summary") or [],
        "envelope": envelope,
        # Honest about the state of her own copy. An owner looking at a
        # ceiling should be able to see whether it is the current one.
        "stale": client.stale(),
        "unreadable": client.unusable(),
        "last_read_error": client.failing,
        "tiers": {tid: view for tid, tier in tiers.items()
                  if (view := org.tier_view(tier, envelope))},
        "governed_resources": sorted(
            rid for rid in RESOURCES if org.reaches(rid, envelope)),
    }


async def pending_invitation(owner: str) -> dict | None:
    """An invitation waiting for her, if there is one.

    Failure is `None` with a note rather than an exception: this is read on
    the way past on an ordinary page load, and an organization being down is
    not a reason her own portal should fail to render.
    """
    if not ORG_ISSUER:
        return None
    try:
        found = await org.invitation(ORG_ISSUER, owner)
    except Exception as exc:                                    # noqa: BLE001
        event("org.invitation_unreadable", owner=owner, error=str(exc))
        return None
    return found if found.get("invited") else None


@app.post("/owner/organization/decline")
async def owner_decline_invitation(request: Request) -> dict:
    """No, thank you — and it is recorded as an answer rather than a silence.

    Her record keeps it too. Being asked to put a layer above her own policy
    is a thing that happened to her, and the fact that she said no is part of
    the account of how her arrangements came to be what they are.
    """
    owner = await require_owner(request)
    found = await pending_invitation(owner)
    if found is None:
        raise HTTPException(status_code=404, detail="nothing is waiting on you")
    await org.decline(ORG_ISSUER, owner, found["code"])
    event("org.invitation_declined", owner=owner, org=found.get("org"))
    await ledger_add(owner, "org_declined", "-", {
        "organization": found.get("name"), "by": found.get("by")})
    return {"declined": found.get("name")}


@app.post("/owner/organization/preview")
async def owner_organization_preview(request: Request) -> dict:
    """What an enrolment code would sign her up to, and what it would do to
    the terms she has already written — before she joins, not after.

    This endpoint is the whole ethical weight of the feature. Every part of
    this system argues that agreeing to something you were never shown is
    not agreement; a governance layer that took effect on a button press and
    explained itself afterwards would be the same failure wearing a suit.
    """
    owner = await require_owner(request)
    if not ORG_ISSUER:
        raise HTTPException(status_code=404,
                            detail="this authority is not configured with an "
                                   "organization to enrol with")
    body = await request.json()
    try:
        envelope = await org.preview(ORG_ISSUER, body.get("code") or "")
        # What it would reach *for her*, so the preview does not promise an
        # organization more than joining would actually give it. She may
        # already hold something jointly, and no charter reaches that.
        envelope = {**envelope, "excluded": sorted(await jointly_held(owner))}
    except Exception as exc:                                    # noqa: BLE001
        raise HTTPException(status_code=400, detail=_org_error(exc))
    # Dry run: what the clamp would do, computed but not applied.
    would = []
    for tier_id, tier in (await st(owner).tiers()).items():
        _, changes = org.clamp(tier, envelope)
        would += [{"tier": tier_id, "tier_name": tier["name"], **c}
                  for c in changes]
    return {"envelope": envelope, "summary": envelope.get("summary") or [],
            # What joining would let them *do*, as distinct from what it
            # requires of her. She has to agree to this before the join is
            # accepted — see below.
            "powers": envelope.get("powers") or {},
            "changes": would,
            "governed_resources": sorted(
                rid for rid in RESOURCES if org.reaches(rid, envelope))}


@app.post("/owner/organization")
async def owner_join_organization(request: Request) -> dict:
    owner = await require_owner(request)
    if not ORG_ISSUER:
        raise HTTPException(status_code=404,
                            detail="this authority is not configured with an "
                                   "organization to enrol with")
    body = await request.json()
    # Agreement, not acknowledgement.
    #
    # This is the one place in the system where somebody voluntarily gives
    # another party standing authority over her own agents — to revoke them,
    # to answer for her, and (where a charter says so) to reach her accounts
    # without asking. Everything else here argues that consent to something
    # you were never shown is not consent; a join that went through on a
    # button press with the disclosure scrolled past would be that failure
    # committed by the system making the argument.
    #
    # So her authority refuses a join that does not carry it, and records
    # what she agreed to alongside the fact that she did. The refusal is not
    # a formality: a portal that forgot to ask would fail here rather than
    # enrol her quietly.
    if not body.get("agreed"):
        raise HTTPException(
            status_code=400,
            detail="joining an organization gives it standing authority over "
                   "your agents. Read what it would be entitled to do, and "
                   "agree to it explicitly, before this can go ahead.")
    try:
        joined = await org.join(ORG_ISSUER, body.get("code") or "", owner,
                               ORG_CALLBACK, body.get("assertion") or "")
    except Exception as exc:                                    # noqa: BLE001
        raise HTTPException(status_code=400, detail=_org_error(exc))
    token = joined.pop("membership_token")
    await st(owner).set_organization({"issuer": ORG_ISSUER, "token": token,
                                      "envelope": joined,
                                      "joined": utcstamp()})
    _ORG[owner] = org.OrgClient(ORG_ISSUER, token, joined)
    event("org.joined", owner=owner, org=joined.get("org"),
          charter_version=joined.get("charter_version"))
    # The record keeps what she agreed to, not merely that she agreed. A
    # charter is versioned and this entry names the version, so "what was I
    # told this would let them do" stays answerable after the organization
    # has edited it a dozen times.
    await ledger_add(owner, "org_joined", "-", {
        "organization": joined.get("name"),
        "charter_version": joined.get("charter_version"),
        "requires": joined.get("summary") or [],
        "agreed_to": [p["what"] for p in
                      (joined.get("powers") or {}).get("can") or []]})
    changes = await clamp_to_envelope(owner, joined, force=True)
    # What she joined for. The organization's resources become things her
    # authority protects — so they appear in her portal, she can write terms
    # over them, and an agent can be told to negotiate for them.
    await resync_shared(owner, joined)
    await owner_notify(owner, {"type": "organization", "state": "joined",
                               "name": joined.get("name")})
    return {"joined": joined.get("org"), "name": joined.get("name"),
            "charter_version": joined.get("charter_version"),
            # What she actually got, which is the half of this she joined for.
            "role": joined.get("role"), "role_name": joined.get("role_name"),
            "grants": joined.get("grants") or [],
            "delegation": joined.get("delegation"),
            "summary": joined.get("summary") or [],
            "changes": [{"tier": c["tier"], "text": c["text"]} for c in changes]}


@app.delete("/owner/organization")
async def owner_leave_organization(request: Request) -> dict:
    owner = await require_owner(request)
    client = await org_client(owner)
    if client is None:
        raise HTTPException(status_code=404, detail="you are not enrolled")
    await client.leave()
    await end_membership(owner, "you left this organization")
    return {"left": True,
            "note": "your terms keep the narrowing this organization "
                    "required. Nothing was widened by leaving; anything you "
                    "want back, you widen yourself."}


def _org_error(exc: Exception) -> str:
    """The organization's own words where there are any.

    A 403 from the enrolment endpoint says the code is wrong, and that is
    the sentence she needs. A connection error says her authority could not
    reach it, which is a different problem with a different fix.
    """
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        try:
            return exc.response.json().get("detail") or exc.response.text
        except Exception:                                       # noqa: BLE001
            return exc.response.text
    return f"the organization could not be reached: {exc}"


# --- Joining a jointly held account -----------------------------------------


async def fetch_mandate(tally: str, account: str) -> dict:
    import httpx

    try:
        async with httpx.AsyncClient(verify=org.CA_BUNDLE or True,
                                     timeout=joint.TALLY_TTL_S) as c:
            r = await c.get(f"{tally.rstrip('/')}/mandate/{account}")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,
                            detail=f"could not read that mandate: {exc}")


def joint_preview_of(mandate: dict, tiers: dict) -> dict:
    """What agreeing would commit her to, and what it would do to terms she
    has already written.

    The second half is the one worth showing. Joining does not change her
    terms — unlike an organization's ceiling, nothing here is clamped into
    her policy — but it does mean the terms an agent is actually held to over
    this resource are hers intersected with everybody else's, and she should
    see which of her own fields her co-owners are about to narrow before she
    agrees rather than afterwards.
    """
    resources = mandate.get("resources") or []
    mine = [t for t in tiers.values()
            if any(joint.claims_match(r, t.get("resources") or [])
                   for r in resources)]
    return {"mandate": mandate, "summary": uma4a_joint.describe(mandate),
            "my_terms": [{"name": t.get("name"),
                          "expires_in": (t.get("terms") or {}).get("expires_in"),
                          "ask_me": bool(t.get("ask_me"))} for t in mine],
            "writes_terms": bool(mine)}


@app.post("/owner/joint/preview")
async def owner_joint_preview(request: Request) -> dict:
    owner = await require_owner(request)
    body = await request.json()
    mandate = await fetch_mandate(body.get("tally") or "", body.get("account") or "")
    return joint_preview_of(mandate, await st(owner).tiers())


@app.post("/owner/joint")
async def owner_joint_join(request: Request) -> dict:
    """Agree to a mandate.

    Refused without an explicit `agreed`, for the reason joining an
    organization is: this hands other people a say over a resource she
    administers, and a party she has never met the standing to ask her
    authorization server questions. Neither is a thing to acquire by
    forgetting to say no.
    """
    owner = await require_owner(request)
    body = await request.json()
    tally = (body.get("tally") or "").rstrip("/")
    account = body.get("account") or ""
    if not body.get("agreed"):
        raise HTTPException(
            status_code=400,
            detail="joining a jointly held account gives its other holders a "
                   "say over what your agents may do with it. Say so explicitly.")
    mandate = await fetch_mandate(tally, account)
    if not any(h.get("owner") == owner for h in mandate.get("holders") or []):
        raise HTTPException(status_code=403,
                            detail="that mandate does not name you as a holder")
    await st(owner).set_mandate(account, joint.record_of(account, tally, mandate))
    # The resources this mandate names have to exist at this authority before
    # she can write terms over them, and they arrive from the resource
    # server's listing rather than from the mandate. Pulled here rather than
    # left to the clock: she agreed to this a second ago and the next thing
    # she will try to do is say what she permits.
    await pull_registrations_now(owner)
    event("joint.joined", owner=owner, account=account, tally=tally,
          holders=[h["owner"] for h in mandate.get("holders") or []])
    await ledger_add(owner, "joint_joined", "-",
                     {"account": account, "tally": tally,
                      "holders": [h["owner"] for h in mandate.get("holders") or []]})
    await owner_notify(owner, {"type": "joint", "state": "joined",
                               "account": account})
    return {"joined": account, "mandate": mandate,
            "summary": uma4a_joint.describe(mandate)}


@app.get("/owner/joint")
async def owner_joint_list(request: Request) -> list:
    owner = await require_owner(request)
    out = []
    for account, record in (await st(owner).mandates()).items():
        mandate = record.get("mandate") or {}
        out.append({
            "account": account,
            "tally": record.get("tally"),
            "resources": mandate.get("resources") or [],
            "holders": [{"owner": h["owner"], "weight": h["weight"]}
                        for h in mandate.get("holders") or []],
            "rule": mandate.get("rule") or {},
            "summary": uma4a_joint.describe(mandate),
        })
    return out


@app.delete("/owner/joint/{account}")
async def owner_joint_leave(account: str, request: Request) -> dict:
    """Stop being a holder.

    What this does not do is end the account. The other holders' mandate is
    theirs, and a party leaving it is a fact for the tally to reflect — this
    server can only stop answering. Her terms stay exactly as they were, for
    the reason leaving an organization leaves its narrowings in place.
    """
    owner = await require_owner(request)
    if not await st(owner).clear_mandate(account):
        raise HTTPException(status_code=404, detail="not a party to that mandate")
    event("joint.left", owner=owner, account=account)
    await ledger_add(owner, "joint_left", "-", {"account": account})
    await owner_notify(owner, {"type": "joint", "state": "left",
                               "account": account})
    return {"left": account}


@app.get("/owner/connections")
async def owner_connections(request: Request) -> list:
    owner = await require_owner(request)
    return await st(owner).connections()


@app.post("/owner/connections/{handle}/revoke")
async def owner_revoke_connection(handle: str, request: Request) -> dict:
    owner = await require_owner(request)
    return await revoke_connection_for(owner, handle, actor=None)


async def revoke_connection_for(owner: str, handle: str,
                                actor: dict | None) -> dict:
    # Deactivating the connection and burning the tokens issued under it is
    # one step, not two: a revocation that flipped the connection and then
    # failed would leave the agent holding exactly the authority Alice had
    # just withdrawn.
    killed = await st(owner).revoke_connection(handle)
    if killed is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    event("connection.revoked", handle=handle, rpts_deactivated=killed,
          by=(actor or {}).get("admin") or owner)
    await ledger_add(owner, "revoked", "-",
                     {"rpts_deactivated": killed,
                      **({"by": actor} if actor else {})}, handle=handle)
    await owner_notify(owner, {"type": "decided", "family": "-",
                               "decision": "revoked", "by": actor})
    return {"handle": handle, "status": "revoked", "rpts_deactivated": killed}


@app.get("/owner/ledger")
async def owner_ledger(request: Request) -> list:
    """The record, or one agent's part of it.

    `?handle=` is what turns a list of negotiations into a trajectory: every
    promise that agent made, every decision she took about it, and everything
    it actually touched, in order."""
    owner = await require_owner(request)
    return await st(owner).ledger(request.query_params.get("handle") or None)


@app.get("/owner/events")
async def owner_events(request: Request):
    """SSE stream for the portal: pending approvals arriving, decisions landing.

    The subscription is the store's, not this process's. Alice's browser
    holds one stream against whichever replica answered her request, while
    the approval she is waiting for may be produced by any of them — so the
    fan-out has to be a property of the state, not of the process that
    happens to be serving her.
    """
    owner = await require_owner(request)
    from sse_starlette.sse import EventSourceResponse

    async def stream():
        async for item in st(owner).subscribe():
            yield {"event": item["type"], "data": json.dumps(item)}

    return EventSourceResponse(stream())
