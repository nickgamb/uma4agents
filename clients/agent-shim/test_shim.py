"""Headless verification of the agent-shim (Spike C runtime half).

Spawns the shim as a stdio MCP server — exactly as Claude Code would — and
drives it with the SDK client:

  1. elicitation path: the client renders Alice's terms and approves them
     (this is what Bob sees inside Claude Code);
  2. tier 3: execute_trade pends until "Alice" approves (owner API, standing
     in for her portal tap);
  3. fallback path: a session *without* elicitation support falls back to
     Bob's standing config (the Claude Desktop case today).
"""

import asyncio
import json
import os
import sys
import threading
import time

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext
from mcp.types import ElicitRequestParams, ElicitResult

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AS_URI = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
OIDC_ISSUER = os.environ.get("UMA4A_OIDC_ISSUER",
                             "https://keycloak.uma.lab/realms/alice")
ALICE_LOGIN = (os.environ.get("ALICE_USERNAME", "alice"),
               os.environ.get("ALICE_PASSWORD", "alice-demo"))
CACERT = os.path.join(REPO, "certs/rootCA.pem")


def alice_token(client: httpx.Client) -> str:
    """The simulated Alice logs in for real: direct-access grant at her IdP."""
    r = client.post(
        f"{OIDC_ISSUER}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "alice-portal",
              "username": ALICE_LOGIN[0], "password": ALICE_LOGIN[1]},
    )
    r.raise_for_status()
    return r.json()["access_token"]

PASS = 0
FAIL = 0
ELICITATIONS: list[str] = []


def check(name: str, ok: bool) -> None:
    global PASS, FAIL
    print(("PASS: " if ok else "FAIL: ") + name, flush=True)
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)


def shim_params(keystore: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(REPO, "clients/agent-shim/shim.py")],
        env={
            **os.environ,
            "PYTHONPATH": os.path.join(REPO, "lib"),
            "UMA4A_CACERT": CACERT,
            "UMA4A_KEYSTORE": keystore,
        },
    )


async def approve_elicitation(
    context: RequestContext, params: ElicitRequestParams
) -> ElicitResult:
    ELICITATIONS.append(params.message)
    print(f"   [bob-sees-in-his-agent]\n{params.message}\n", flush=True)
    return ElicitResult(action="accept", content={"approve": True})


def simulate_alice_approval(count: int = 1) -> None:
    """Approve the next `count` pending items (connection requests and
    operation approvals alike) — standing in for Alice's portal taps."""
    client = httpx.Client(verify=CACERT, timeout=10.0)
    headers = {"Authorization": f"Bearer {alice_token(client)}"}
    approved = 0
    for _ in range(60):
        time.sleep(1.0)
        pending = client.get(
            f"{AS_URI}/owner/pending", headers=headers,
        ).json()
        for p in pending:
            print(f"   [simulated-alice] approving {p['kind']} {p['family']}", flush=True)
            client.post(
                f"{AS_URI}/owner/pending/{p['family']}/decision",
                json={"decision": "approved"},
                headers=headers,
            )
            approved += 1
            if approved >= count:
                return


async def elicitation_session() -> None:
    async with stdio_client(shim_params("/tmp/shim-key-elicit.pem")) as (read, write):
        async with ClientSession(
            read, write, elicitation_callback=approve_elicitation
        ) as session:
            await session.initialize()
            tools = await session.list_tools()
            check("shim exposes the vault tools", len(tools.tools) == 3)

            # First contact: this key has no standing connection, so tier 1
            # pends until "Alice" connects the agent.
            threading.Thread(target=simulate_alice_approval, daemon=True).start()
            r = await session.call_tool("get_positions", {})
            text = r.content[0].text if r.content else ""
            check("first contact connects, then tier 1 grants", "VTI" in text)
            check("terms were rendered inside the agent", len(ELICITATIONS) >= 1
                  and "prohibited" in ELICITATIONS[0])

            threading.Thread(target=simulate_alice_approval, daemon=True).start()
            r = await session.call_tool(
                "execute_trade", {"symbol": "BND", "side": "buy", "quantity": 10}
            )
            text = r.content[0].text if r.content else ""
            check("tier 3 pends, Alice approves, trade executes", "executed" in text)


async def fallback_session() -> None:
    async with stdio_client(shim_params("/tmp/shim-key-fallback.pem")) as (read, write):
        async with ClientSession(read, write) as session:  # no elicitation support
            await session.initialize()
            # Fresh key -> fresh connection request on first contact.
            threading.Thread(target=simulate_alice_approval, daemon=True).start()
            r = await session.call_tool("get_transactions", {"account": "brokerage-main"})
            text = r.content[0].text if r.content else ""
            check("standing-config fallback (no elicitation client)", "brokerage-main" in text)


async def main() -> int:
    print("== elicitation-capable client (the Claude Code case) ==", flush=True)
    await elicitation_session()
    print("== client without elicitation (the Claude Desktop case today) ==", flush=True)
    await fallback_session()
    print(f"\nshim-test: {PASS} passed, {FAIL} failed", flush=True)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
