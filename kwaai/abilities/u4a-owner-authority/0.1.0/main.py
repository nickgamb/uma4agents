#!/usr/bin/env python3
"""The ability's entry point, run by pAI-OS as `scripts.start`.

pAI-OS starts an ability as a process and configures it with environment
variables — the abilities README says so plainly: "This may include setting
environment variables, editing configuration files, or providing necessary
API keys." So this reads its configuration from the environment, holds the
person's key, and answers her authorization server when an agent asks for
something of hers.

Nothing here implements the grant. The ticket, the terms, the signed
agreement, the token and the ledger all stay with her authorization server;
this decides, which is the one thing only she can do.

    U4A_AUTHORITY_URL    her authorization server
    U4A_AUTHORITY_NAME   the authority her request signature is rebuilt
                         against; must match UMA_AS_OWNER_AUTHORITY there
    U4A_OWNER_KEY        her signing key
    U4A_AUTO_TIERS       tiers to answer without asking (empty by default)
    U4A_CA_BUNDLE        trust bundle, if her authority is behind a private CA
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The ability ships beside the shared implementation rather than vendoring a
# copy of it: same code as `make kwaai-check` runs, so the thing demonstrated
# inside pAI-OS is the thing that is tested.
sys.path.insert(0, os.environ.get("U4A_ABILITY_LIB", "/opt/u4a/ability"))
sys.path.insert(0, os.environ.get("U4A_LIB", "/opt/u4a/lib"))

import httpx  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

from u4a_authority import OwnerAuthority, Request  # noqa: E402

AUTHORITY_URL = os.environ.get("U4A_AUTHORITY_URL", "https://alice-as.uma.lab")
AUTHORITY_NAME = os.environ.get("U4A_AUTHORITY_NAME", "alice-as.uma.lab")
KEY_PATH = os.environ.get("U4A_OWNER_KEY", "/owner/owner-ed25519.pem")
AUTO = tuple(t for t in os.environ.get("U4A_AUTO_TIERS", "").split(",") if t)
CA = os.environ.get("U4A_CA_BUNDLE")


class PaiosHost:
    """The four things the ability needs, supplied the way pAI-OS supplies them.

    pAI-OS has no capability grants — an ability is an installed process,
    configured by environment, not a sandbox handed a key service and a
    channel to its person. So this ability brings its own: a key from a file,
    and a decision log on stdout that pAI-OS captures.

    What a host *could* provide instead is the interesting question, and it is
    the one worth putting to Kwaai rather than assuming. `sign` never returns
    private key material, so a host-held key — an enclave, a passkey, the
    webauthn support already in their backend — would drop straight in.
    """

    def __init__(self, key_path: str) -> None:
        with open(key_path, "rb") as fh:
            self._key = serialization.load_pem_private_key(fh.read(), password=None)

    def sign(self, payload: bytes) -> bytes:
        return self._key.sign(payload)

    def public_key_pem(self) -> bytes:
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def ask(self, request: Request) -> bool:
        """Where a real personal AI would reach its person.

        pAI-OS gives an ability no channel to the human, so this records the
        question and refuses. Refusing is the right default: the pend exists
        because she has not said yes, and an ability that cannot ask her must
        not answer for her.

        `U4A_AUTO_TIERS` is the escape hatch, and it is standing consent she
        configured rather than a decision this process invented.
        """
        self.log("cannot-ask", {"family": request.family,
                                "summary": request.summary(),
                                "outcome": "denied — no channel to her"})
        return False

    def log(self, event: str, detail: dict) -> None:
        line = json.dumps({"ability": "u4a-owner-authority",
                           "event": event, **detail})
        print(line, flush=True)
        # Also to a file, so a check can read what the ability decided without
        # scraping container logs from outside.
        path = os.environ.get("U4A_ABILITY_LOG")
        if path:
            try:
                with open(path, "a") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass


def main() -> int:
    if not Path(KEY_PATH).exists():
        print(json.dumps({"ability": "u4a-owner-authority", "event": "no-key",
                          "detail": f"no owner key at {KEY_PATH}"}), flush=True)
        return 1

    host = PaiosHost(KEY_PATH)
    ability = OwnerAuthority(host=host, authority_url=AUTHORITY_URL,
                             authority_name=AUTHORITY_NAME,
                             auto_approve_tiers=AUTO)
    host.log("started", {"authority": AUTHORITY_URL,
                         "standing_approval": list(AUTO)})

    with httpx.Client(verify=CA or True) as client:
        try:
            ability.run(poll_seconds=2.0, client=client)
        except KeyboardInterrupt:
            host.log("stopped", {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
