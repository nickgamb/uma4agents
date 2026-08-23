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

Idempotent: the Secret is created only if absent, so re-applying the lab never
rotates a key underneath a running pod.
"""
import base64, json, os, ssl, sys, urllib.request

NAME = sys.argv[1]                 # secret name
AGENTS = sys.argv[2:]              # one keypair per agent named here
NS = os.environ["POD_NAMESPACE"]   # from the pod, never defaulted

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
with open(f"{SA}/token") as f:
    token = f.read().strip()
api = "https://kubernetes.default.svc"
ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")


def call(method, path, body=None):
    req = urllib.request.Request(
        api + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    return urllib.request.urlopen(req, context=ctx)


try:
    call("GET", f"/api/v1/namespaces/{NS}/secrets/{NAME}")
    print(f"{NAME} already exists; leaving it alone")
    raise SystemExit(0)
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

data, keys = {}, []
for agent in AGENTS:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    data[f"{agent}-ed25519.pem"] = base64.b64encode(pem).decode()
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    keys.append({
        "kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "use": "sig",
        "kid": f"agent-{agent}-1",
        "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
    })

# The published document: public halves only. The operator is given this and
# nothing else — it serves a directory and has no use for a private key.
data["agent-jwks.json"] = base64.b64encode(
    json.dumps({"keys": keys}).encode()).decode()

call("POST", f"/api/v1/namespaces/{NS}/secrets", {
    "apiVersion": "v1", "kind": "Secret", "metadata": {"name": NAME},
    "data": data,
})
print(f"{NAME} created with {len(AGENTS)} agent key(s): {', '.join(AGENTS)}")
