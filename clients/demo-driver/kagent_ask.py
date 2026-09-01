"""Ask an agent framework a question, and watch Alice's policy answer it.

This is the adoption case. kagent is not ours, was not modified, and has never
heard of UMA. It has one tool server configured — the U4A adapter running in
Bob's namespace — and it believes those are ordinary MCP tools.

What this file does is ask a question over kagent's A2A endpoint, and play
Alice while the request is held. What it deliberately does *not* do is any part
of the grant: no key, no ticket, no terms, no signature. Those all happen in
the adapter, which is the point.

    make kagent-check
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

import httpx

A2A = os.environ.get("KAGENT_A2A")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/certs/rootCA.pem")
QUESTION = os.environ.get("KAGENT_QUESTION", "What is in Alice's portfolio?")
# Whether to answer her pending queue on her behalf. On by default, because
# `make kagent-check` runs headless and something has to say yes. Off when a
# person is at her portal, which is the only way to show that the wait is real.
SIM = os.environ.get("KAGENT_SIM", "1") != "0"

# How long the requesting side keeps checking, and how often. The owner may be
# asleep, and nothing here holds a connection open while she is.
#
# Unhurried on purpose. Checking is cheap — the adapter resumes the request she
# is already deciding rather than opening another one — but a check that fails
# to resume falls back to negotiating, and *that* spends a slice of the
# attention budget her authority keeps per agent. Asking every few seconds is
# how a well-meaning agent turns into the thing she throttles.
POLL_FOR_S = int(os.environ.get("KAGENT_POLL_FOR", "1800"))
POLL_EVERY_S = int(os.environ.get("KAGENT_POLL_EVERY", "45"))


def _is_pending(body: dict) -> bool:
    """Did the agent come back still waiting on her?

    Read off the adapter's own word rather than the model's prose, which
    varies with the model and cannot be relied on.
    """
    return "PENDING" in json.dumps(body).upper()


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def owner_token(c: httpx.Client) -> str:
    return c.post(
        f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "meridian-portal",
              "username": "alice", "password": "alice-demo"},
    ).json()["access_token"]


def touched_count() -> int:
    """How many times her resources have actually been reached.

    This is the assertion that matters. "The agent replied without erroring"
    is not evidence: a model that chats about portfolios without calling a
    tool produces a perfectly cheerful answer and proves nothing. A new
    `touched` row in her ledger means the grant was issued and spent.
    """
    ca = CA if os.path.exists(CA) else True
    try:
        with httpx.Client(verify=ca, timeout=20.0) as c:
            h = {"Authorization": f"Bearer {owner_token(c)}"}
            led = c.get(f"{AS_PUBLIC}/owner/ledger", headers=h).json()
            return sum(1 for e in led if e.get("kind") == "touched")
    except Exception:                                              # noqa: BLE001
        return -1


def simulate_alice(seconds: float) -> threading.Event:
    """Her side, with her own credential, exactly as her portal does it.

    Present because the agent asking is one she has never met, and a first
    contact is held for her however permissive the tier. `SIM=0` in the other
    demos leaves this tap to a person; a headless check has to answer.
    """
    stop = threading.Event()

    def loop() -> None:
        ca = CA if os.path.exists(CA) else True
        deadline = time.time() + seconds
        with httpx.Client(verify=ca, timeout=15.0) as c:
            while time.time() < deadline and not stop.is_set():
                try:
                    tok = c.post(
                        f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                        data={"grant_type": "password", "client_id": "meridian-portal",
                              "username": "alice", "password": "alice-demo"},
                    ).json()["access_token"]
                    h = {"Authorization": f"Bearer {tok}"}
                    for p in c.get(f"{AS_PUBLIC}/owner/pending", headers=h).json():
                        say(f"[alice] approving {p['kind']} request for {p['tier']}")
                        c.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                               json={"decision": "approved"}, headers=h)
                except Exception:                                  # noqa: BLE001
                    pass
                time.sleep(1)

    threading.Thread(target=loop, daemon=True).start()
    return stop


def main() -> int:
    if not A2A:
        print("KAGENT_A2A is not set"); return 1

    before = touched_count()
    approving = simulate_alice(420) if SIM else None
    print("\n== An agent framework, asked a question ==")
    say(f"agent: sterling-vance/advisory-agent (kagent)")
    say(f"question: {QUESTION}")
    say("it has one tool server: the U4A adapter. It knows nothing else.")
    if not SIM:
        say("[alice] nobody is answering for her — decide it in her portal.")

    def send() -> dict | int:
        payload = {
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "message/send",
            "params": {"message": {
                "role": "user", "messageId": uuid.uuid4().hex,
                "parts": [{"kind": "text", "text": QUESTION}],
            }},
        }
        with httpx.Client(timeout=420.0) as c:
            r = c.post(A2A, json=payload)
            if r.status_code >= 400:
                print(f"FAIL: the agent could not be reached: "
                      f"{r.status_code} {r.text[:200]}")
                return r.status_code
            return r.json()

    # Ask, and keep asking while the answer is "she has not decided yet".
    #
    # The wait belongs to the owner, not to a socket: the adapter hands a pend
    # back as a result so nothing has to hold a connection open across it, and
    # what closes the loop is somebody asking again. A capable model does that
    # by itself when a tool says PENDING; a small one says something reassuring
    # and stops, which looks identical to a refusal and is not one. So the
    # asking side polls too, and the demo works either way.
    #
    # Each attempt resumes the same pend at her authority rather than opening a
    # second one, so she sees one request no matter how many times it is
    # checked.
    deadline = time.time() + POLL_FOR_S
    attempt = 0
    while True:
        attempt += 1
        body = send()
        if isinstance(body, int):
            return 1
        if SIM or not _is_pending(body) or time.time() > deadline:
            break
        say(f"[pending] she has not answered yet — asking again "
            f"(attempt {attempt + 1})")
        time.sleep(POLL_EVERY_S)

    if approving is not None:
        approving.set()
    text = json.dumps(body)
    print("\n== What it came back with ==")
    # A2A echoes the prompt back inside the task as well as the reply, and the
    # reply appears under both `artifacts` and `history`. Dedupe, keeping order.
    seen = set()
    for part in _texts(body):
        if part in seen or part.strip() == QUESTION.strip():
            continue
        seen.add(part)
        print(f"   {part[:600]}")

    if "error" in body:
        print(f"\nFAIL: the agent errored: {text[:300]}")
        return 1

    after = touched_count()
    print(f"\n== And on Alice's side ==")
    say(f"her ledger's `touched` rows: {before} before, {after} after")

    if not SIM:
        # A person answered this one, so both outcomes are correct and neither
        # is a failure. Refusing a trade is the tier working, not the run
        # breaking, and asserting otherwise would make the most important beat
        # of the demo look like a bug.
        if after > before:
            print("\nHer policy allowed it, and her resources were reached.")
        else:
            print("\nHer resources were not reached — she declined, or has not")
            print("answered yet. Both are her decision, and the agent stopped.")
        return 0

    if after <= before:
        print("\nFAIL: the agent answered without ever reaching her resources.")
        print("      A model that talks about a portfolio without calling a tool")
        print("      proves nothing — the grant was never issued or never spent.")
        return 1

    print("\nPASS: kagent asked, the adapter negotiated, Alice's policy decided,")
    print("      and her resources were actually reached. The framework was not")
    print("      modified to do any of it.")
    return 0


def _texts(node) -> list:
    """Pull the text parts out of whatever A2A wrapped them in."""
    out = []
    if isinstance(node, dict):
        if node.get("kind") == "text" and "text" in node:
            out.append(node["text"])
        for v in node.values():
            out += _texts(v)
    elif isinstance(node, list):
        for v in node:
            out += _texts(v)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
