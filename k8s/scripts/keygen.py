"""Create an Ed25519 signing key as a Secret, once.

Loaded into each namespace that needs it as the `keygen-script` ConfigMap
(see Makefile.k8s). One copy: the parties are separate, the arithmetic is
not, and three drifting transcriptions of the same forty lines is how one
of them quietly stops writing the public half.
"""
import base64, json, os, ssl, sys, urllib.request

NAME = sys.argv[1]          # secret name
FILENAME = sys.argv[2]      # key within the secret, and the mounted filename
# A third argument asks for the public half alongside the private one.
# The owner's device key needs both and they go to different places: the
# private half is mounted into her personal AI, the public half into her
# authorization server, which is the whole point of it being a key she
# holds rather than a credential she is issued.
PUBNAME = sys.argv[3] if len(sys.argv) > 3 else None
# From the pod, never defaulted. A default is right in one namespace and
# silently writes another party's Secret in the rest, which is the kind of
# mistake that looks like it worked.
NS = os.environ["POD_NAMESPACE"]

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

key = Ed25519PrivateKey.generate()
pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption())

data = {FILENAME: base64.b64encode(pem).decode()}
if PUBNAME:
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)
    data[PUBNAME] = base64.b64encode(pub).decode()
call("POST", f"/api/v1/namespaces/{NS}/secrets", {
    "apiVersion": "v1", "kind": "Secret", "metadata": {"name": NAME},
    "data": data,
})
print(f"{NAME} created")
