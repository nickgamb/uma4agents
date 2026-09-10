"""Provision the requesting side's agent keys, once.

An operator's key directory is a JWKS of the keys *its own agents* sign with.
That is a document it holds because it issued those keys — not one that fills
up as agents introduce themselves. This script is the issuing step: it
generates a keypair per named agent and writes one Secret holding every
private half plus the single public document the operator serves.

Two properties follow, and both are the reason this exists rather than a
runtime registration endpoint:

  * every replica of the operator serves the same bytes, because they all
    mount the same document. A directory collected at runtime lives in one
    process's memory, so with two replicas an agent registers with one and a
    resource server asks the other — which shows up as an agent losing an
    assurance level about half the time, and nothing logs a reason.
  * an agent signs with a key its operator really published, which is the
    claim accountability level 2 is supposed to encode. An agent that can put
    its own key in the directory is attesting to itself.

Idempotent, and specifically idempotent *per agent*. Re-applying the lab never
rotates a key underneath a running pod — but an agent added to the list after
the Secret exists is generated and patched in, and the published document is
rebuilt to include it.

Skipping wholesale on the Secret's existence was the earlier behaviour and it
had a bad failure mode: adding an agent name silently did nothing, so the new
agent's key was absent from a directory that still returned 200, and the only
symptom was an agent stuck an assurance level below where it should be. The
alternative — deleting the Secret to force a regeneration — rotates the
existing agents' keys and destroys the standing their checks depend on.
"""
import base64, json, os, ssl, sys, urllib.request

NAME = sys.argv[1]                 # secret name
_rest = sys.argv[2:]
# Names after `--rotate` are regenerated on every run. That is the difference
# between a long-lived agent and an ephemeral one, and the lab needs both: a
# lead agent's key has to be stable, because the standing an owner builds with
# it is keyed by that key, while a worker spawned for one job gets a fresh key
# the way a real orchestrator's would. Without the second kind, a check that
# revokes a worker can never run twice — the revocation is permanent, and it
# should be.
if "--rotate" in _rest:
    _i = _rest.index("--rotate")
    AGENTS, ROTATE = _rest[:_i], _rest[_i + 1:]
else:
    AGENTS, ROTATE = _rest, []
AGENTS = AGENTS + ROTATE
NS = os.environ["POD_NAMESPACE"]   # from the pod, never defaulted

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
with open(f"{SA}/token") as f:
    token = f.read().strip()
api = "https://kubernetes.default.svc"
ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")


def call(method, path, body=None, content_type="application/json"):
    req = urllib.request.Request(
        api + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": content_type})
    return urllib.request.urlopen(req, context=ctx)


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

existing = {}
try:
    with call("GET", f"/api/v1/namespaces/{NS}/secrets/{NAME}") as r:
        existing = json.load(r).get("data") or {}
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise


def public_jwk(pem_b64: str, agent: str) -> dict:
    key = serialization.load_pem_private_key(
        base64.b64decode(pem_b64), password=None)
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "use": "sig",
            "kid": f"agent-{agent}-1",
            "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode()}


# Keep every key that is already there, generate only what is missing. The
# public document is rebuilt from the private halves rather than carried
# forward, so it cannot drift from the keys the Secret actually holds.
data, keys, added, rotated = {}, [], [], []
for agent in AGENTS:
    field = f"{agent}-ed25519.pem"
    if field in existing and agent not in ROTATE:
        data[field] = existing[field]
    else:
        key = Ed25519PrivateKey.generate()
        data[field] = base64.b64encode(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())).decode()
        (rotated if field in existing else added).append(agent)
    keys.append(public_jwk(data[field], agent))

# The published document: public halves only. The operator is given this and
# nothing else — it serves a directory and has no use for a private key.
data["agent-jwks.json"] = base64.b64encode(
    json.dumps({"keys": keys}).encode()).decode()

if not existing:
    call("POST", f"/api/v1/namespaces/{NS}/secrets", {
        "apiVersion": "v1", "kind": "Secret", "metadata": {"name": NAME},
        "data": data,
    })
    print(f"{NAME} created with {len(AGENTS)} agent key(s): {', '.join(AGENTS)}")
elif added or rotated:
    # A JSON Patch naming only the agents that were missing or were asked for
    # by name under `--rotate`. A long-lived agent's key has no operation
    # naming it, so this cannot rewrite one however the loop above is later
    # changed — the guarantee is in the shape of the request rather than in a
    # comment. The published document is the one other field that changes,
    # because it is derived from the keys rather than being one of them.
    ops = [{"op": "add", "path": f"/data/{a}-ed25519.pem",
            "value": data[f"{a}-ed25519.pem"]} for a in added]
    ops += [{"op": "replace", "path": f"/data/{a}-ed25519.pem",
             "value": data[f"{a}-ed25519.pem"]} for a in rotated]
    ops.append({"op": "replace", "path": "/data/agent-jwks.json",
                "value": data["agent-jwks.json"]})
    call("PATCH", f"/api/v1/namespaces/{NS}/secrets/{NAME}", ops,
         content_type="application/json-patch+json")
    what = []
    if added:
        what.append(f"{len(added)} added ({', '.join(added)})")
    if rotated:
        what.append(f"{len(rotated)} rotated ({', '.join(rotated)})")
    print(f"{NAME}: {'; '.join(what)}; every other key untouched")
else:
    print(f"{NAME} already holds every named agent; leaving it alone")
