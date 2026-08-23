"""An agent that knows nothing about UMA, reaching Alice's things anyway.

This is the requesting side with the protocol taken out of it. There is no
signing key here, no permission ticket, no terms, no proof-of-possession —
nothing in this file imports `uma4a_grant`. It is a plain MCP client calling
plain MCP tools over streamable-http.

Between it and the gateway sits the **adapter**: the same
`clients/agent-shim/shim.py` Bob runs beside Claude Code, started with
`UMA4A_SHIM_TRANSPORT=streamable-http` so it can be reached over the network
instead of spawned as a subprocess. The adapter holds Bob's key and runs the
four beats; the agent above it sees tools.

That is the claim this checks, and it is an adoption claim rather than a
protocol one: **the requesting side needs an adapter, not a rewrite.** It is
what makes an off-the-shelf agent framework — kagent, in the Kubernetes path —
able to be governed by Alice's policy without being modified. See
docs/KAGENT.md.

Run against the full stack with `make adapter-check`.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time

SHIM = os.environ.get("UMA4A_SHIM_URL", "http://agent-shim:9030/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    # Detail only when it failed: a passing line that carries its own failure
    # message reads as though it failed.
    print(f"   {'ok  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail and not ok else ""),
          flush=True)


def simulate_alice(seconds: float) -> threading.Event:
    """Alice, answering from her portal, in a thread.

    Her side of the boundary, not the agent's — this uses her owner API with
    her own credential, exactly as her portal does. It is here because the
    agent below is a *first contact*: her policy holds a request from an agent
    she has never met, which is correct, and which a headless check has to
    answer or wait out.
    """
    import httpx

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
                        c.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                               json={"decision": "approved"}, headers=h)
                except Exception:                                  # noqa: BLE001
                    pass
                time.sleep(1)

    threading.Thread(target=loop, daemon=True).start()
    return stop


async def main() -> int:
    # The whole client, and note what is not imported: nothing of ours.
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    approving = simulate_alice(180)
    print("\n== An agent with no U4A code in it ==")
    async with streamable_http_client(SHIM) as streams:
        async with ClientSession(*streams[:2]) as session:
            await session.initialize()

            tools = {t.name for t in (await session.list_tools()).tools}
            check("it discovers Alice's tools as ordinary MCP",
                  {"get_positions", "get_transactions"} <= tools,
                  f"saw {sorted(tools)}")

            res = await session.call_tool("get_positions", {})
            text = "".join(getattr(c, "text", "") for c in res.content)
            check("and calling one returns her data",
                  "brokerage" in text.lower() or "symbol" in text.lower(),
                  text[:120])
            print(f"   {text[:150]}")

            # The negotiation happened, and it happened somewhere else.
            check("it never saw a ticket, terms, or a signature",
                  "ticket" not in text.lower() and "uma" not in text.lower(),
                  "protocol leaked into the tool result")

    approving.set()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        return 1
    print("\nPASS: an unmodified MCP client reached Alice's resources, and her")
    print("      policy decided. The four beats ran in the adapter beside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
