#!/usr/bin/env python3
"""Alice's side of her own authorization server, with no identity provider.

She holds an Ed25519 key. Every owner-API request is signed with it under
RFC 9421 — the same message-signature profile agents use to prove possession
of a grant, pointed the other way. The authority verifies one public key.

That is the whole credential story. There is no login, no session, no bearer
token, nothing issued and nothing to revoke centrally: if she wants a new
credential she makes a new key and enrols it.

    python owner.py key                    print her public key, to enrol
    python owner.py pending                what is waiting on her
    python owner.py approve <family>       let it through
    python owner.py deny <family>          refuse it
    python owner.py policy                 her tiers
    python owner.py resources              what her authority is protecting
    python owner.py connections            standing agent relationships
    python owner.py revoke <handle>        end one, and burn its live grants
    python owner.py ledger                 promised / approved / touched
    python owner.py watch                  block until something needs her

Environment:
    UMA4A_OWNER_AS          her authorization server   (http://localhost:9000)
    UMA4A_OWNER_KEY         her private key            (~/.uma4agents/owner-key.pem)
    UMA4A_OWNER_AUTHORITY   the authority the AS reconstructs the signature
                            base against; must match UMA_AS_OWNER_AUTHORITY
                            on the server side
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))

import httpx  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from uma4a_http_sig import sign as http_sign  # noqa: E402

AS = os.environ.get("UMA4A_OWNER_AS", "http://localhost:9000").rstrip("/")
KEY_PATH = os.environ.get(
    "UMA4A_OWNER_KEY", os.path.expanduser("~/.uma4agents/owner-key.pem")
)
# Taken from configuration on both sides. An authority read off the request is
# an authority the caller chooses, which is the bug this profile keeps warning
# about — it is no different when the caller is the owner.
AUTHORITY = os.environ.get("UMA4A_OWNER_AUTHORITY", "alice-as.uma.lab")


def load_key() -> Ed25519PrivateKey:
    """Her key, made on first use.

    A real deployment enrols a key the device already holds — a passkey, a
    secure enclave, whatever she authenticates to her own hardware with. This
    writes a file, because the point of the lab is that nothing has to be set
    up first, and the protocol cannot tell the difference.
    """
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as fh:
            return serialization.load_pem_private_key(fh.read(), password=None)

    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as fh:
        fh.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    os.chmod(KEY_PATH, 0o600)
    pub_path = KEY_PATH.replace(".pem", ".pub")
    with open(pub_path, "wb") as fh:
        fh.write(
            key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    print(f"# made a new owner key at {KEY_PATH}", file=sys.stderr)
    print(f"# enrol the public half from {pub_path}", file=sys.stderr)
    return key


def call(method: str, path: str, body: dict | None = None) -> httpx.Response:
    key = load_key()
    # The exact bytes are signed and sent. Serialising twice — once to hash,
    # once for httpx — would risk hashing something the server never sees.
    raw = json.dumps(body).encode() if body is not None else None
    headers = http_sign(
        method=method,
        authority=AUTHORITY,
        path=path,
        authorization="",
        key=key,
        keyid="owner",
        body=raw,
    )
    headers["Accept"] = "application/json"
    if raw is not None:
        headers["Content-Type"] = "application/json"
    with httpx.Client(timeout=30.0) as client:
        return client.request(method, f"{AS}{path}", headers=headers, content=raw)


def show(resp: httpx.Response) -> int:
    if resp.status_code >= 400:
        print(f"{resp.status_code} {resp.text}", file=sys.stderr)
        return 1
    try:
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print(resp.text)
    return 0


def cmd_key() -> int:
    load_key()
    pub_path = KEY_PATH.replace(".pem", ".pub")
    with open(pub_path) as fh:
        print(fh.read().strip())
    return 0


def cmd_pending() -> int:
    resp = call("GET", "/owner/pending")
    if resp.status_code >= 400:
        return show(resp)
    items = resp.json()
    if not items:
        print("nothing is waiting on you")
        return 0
    for it in items:
        op = it.get("operation") or {}
        print(f"{it['family']}  {it.get('kind', 'operation')}  tier={it.get('tier')}")
        print(f"  purpose:   {it.get('purpose')}")
        if op:
            print(f"  operation: {op.get('tool')}({json.dumps(op.get('params', {}))})")
        print(f"  agent:     {it.get('identity')}")
        if it.get("prohibited"):
            print(f"  prohibited: {', '.join(it['prohibited'])}")
        print()
    return 0


def cmd_decide(family: str, decision: str) -> int:
    return show(call("POST", f"/owner/pending/{family}/decision",
                     {"decision": decision}))


def cmd_watch() -> int:
    """Poll until something needs her.

    Deliberately a poll rather than the event stream: this is the smallest
    thing that works, and it keeps the client honest about being a stand-in
    for a surface that would push.
    """
    print("watching for requests — ctrl-c to stop", file=sys.stderr)
    seen: set[str] = set()
    while True:
        resp = call("GET", "/owner/pending")
        if resp.status_code < 400:
            for it in resp.json():
                if it["family"] not in seen:
                    seen.add(it["family"])
                    print(f"\n>>> {it.get('kind', 'operation')} needs you: "
                          f"{it.get('purpose')}")
                    op = it.get("operation") or {}
                    if op:
                        print(f"    {op.get('tool')}"
                              f"({json.dumps(op.get('params', {}))})")
                    print(f"    approve with: python owner.py approve {it['family']}")
        time.sleep(2)


COMMANDS = {
    "key": lambda a: cmd_key(),
    "pending": lambda a: cmd_pending(),
    "approve": lambda a: cmd_decide(a[0], "approved"),
    "deny": lambda a: cmd_decide(a[0], "denied"),
    "policy": lambda a: show(call("GET", "/owner/policies")),
    "resources": lambda a: show(call("GET", "/owner/resources")),
    "connections": lambda a: show(call("GET", "/owner/connections")),
    "revoke": lambda a: show(call("POST", f"/owner/connections/{a[0]}/revoke")),
    "ledger": lambda a: show(call("GET", "/owner/ledger")),
    "watch": lambda a: cmd_watch(),
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    try:
        return COMMANDS[sys.argv[1]](sys.argv[2:])
    except IndexError:
        print(f"{sys.argv[1]} needs an argument — see the usage above",
              file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
