"""A personal AI, reduced to the four things the ability needs from one.

pAI-OS would be the host here. This stands in for it so the binding is
runnable and reviewable today, and so the call with Kwaai is about mapping
four named requirements onto their actual mechanism rather than starting from
a blank page.

What it does that a real host would do properly:

    sign / public_key   holds her Ed25519 key in a file. A real host holds it
                        in an enclave, or behind a passkey, and never returns
                        the private half — which the ability already assumes,
                        because it only ever calls sign().
    ask                 prints the request and reads a line. A real host has
                        her attention: a notification, a voice turn, a watch
                        face. The wait is unbounded either way.
    log                 prints. A real host has somewhere to put a record.

Run it against the fixture:

    make fixture
    make kwaai-host                    # asks you about each request
    make kwaai-host AUTO=tier1         # answers tier1 without asking

and then, from another terminal, drive an agent at the vault.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ability"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from u4a_authority import OwnerAuthority, Request  # noqa: E402

KEY_PATH = os.environ.get("UMA4A_OWNER_KEY", "/keys/owner-ed25519.pem")
AUTHORITY_URL = os.environ.get("UMA4A_OWNER_AS", "http://uma-as:9000")
AUTHORITY_NAME = os.environ.get("UMA4A_OWNER_AUTHORITY", "alice-as.local")
AUTO = tuple(t for t in os.environ.get("UMA4A_AUTO_TIERS", "").split(",") if t)


class DemoHost:
    """The stand-in. Four methods, because that is all the ability asks for."""

    def __init__(self, key_path: str) -> None:
        with open(key_path, "rb") as fh:
            self._key: Ed25519PrivateKey = serialization.load_pem_private_key(
                fh.read(), password=None)

    def sign(self, payload: bytes) -> bytes:
        return self._key.sign(payload)

    def public_key_pem(self) -> bytes:
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def ask(self, request: Request) -> bool:
        print("\n" + "─" * 68)
        print(f"  {request.summary()}")
        print(f"  agent:  {request.agent}")
        print(f"  tier:   {request.tier}   ({request.kind})")
        if request.prohibited:
            print(f"  agreed not to:  {', '.join(request.prohibited)}")
        print("─" * 68)
        try:
            answer = input("  approve? [y/N] ").strip().lower()
        except EOFError:
            # No one is at the keyboard. Refusing is the safe answer, and it
            # is also the correct one: the point of the pend is that she has
            # not said yes.
            print("  (no input available — denying)")
            return False
        return answer in ("y", "yes")

    def log(self, event: str, detail: dict) -> None:
        print(json.dumps({"host": "kwaai-demo", "event": event, **detail}),
              flush=True)


def main() -> int:
    host = DemoHost(KEY_PATH)
    ability = OwnerAuthority(
        host=host,
        authority_url=AUTHORITY_URL,
        authority_name=AUTHORITY_NAME,
        auto_approve_tiers=AUTO,
    )
    print("personal AI up — holding her key, watching her authority")
    print(f"  authority: {AUTHORITY_URL}")
    if AUTO:
        print(f"  standing approval for: {', '.join(AUTO)}")
    print("  everything else will be put to you\n")
    try:
        ability.run()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
