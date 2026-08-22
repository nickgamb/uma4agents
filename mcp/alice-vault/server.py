"""alice-vault-mcp — Alice's brokerage vault as an MCP server.

Fixture data through a real protocol path: positions, transaction history,
and a pretend trade-execution endpoint, served over MCP streamable-http.

Whether this server handles its own authorization, or something in front of it
does, is a deployment choice. UMA's FedAuthz gives the resource server a job
list and never says which piece of software has to do it, so this server runs
both ways, selected by ENFORCEMENT_MODE:

  gateway  (default) — this process holds no auth code at all; an ext_authz
                       service ahead of it carries the obligations.
  embedded           — the same enforcement core runs in-process as an MCP
                       SDK 2.x Extension (see uma_extension.py), and there
                       need be no gateway in the path.

Same authorization server, same ticket, same terms, same token in both. The
one visible difference is beat 1's envelope: a gateway can answer 401 +
WWW-Authenticate, an in-process interceptor has to raise a JSON-RPC error
carrying the same ticket. That asymmetry is the finding, not a compromise.
"""

import json
import os
import pathlib

from mcp.server.mcpserver import MCPServer

# Whose vault this process is. One instance per owner: her holdings are not
# rows in a table somebody else can also reach, they are a different process
# with a different fixture file, reached at a different address. A resource
# server with a thousand clients has a thousand of these, however it chooses
# to pack them.
VAULT_OWNER = os.environ.get("UMA_VAULT_OWNER", "alice")
FIXTURES = json.loads(pathlib.Path(
    os.environ.get("UMA_VAULT_FIXTURES",
                   str(pathlib.Path(__file__).parent / "fixtures.json"))
).read_text())

# The tool surface, and which calls are single-use. In gateway mode the PEP
# holds the same table; in embedded mode this is the one copy.
TOOLS = {
    "get_positions": (f"{VAULT_OWNER}-vault/get_positions", ["positions:read"]),
    "get_transactions": (f"{VAULT_OWNER}-vault/get_transactions",
                         ["transactions:read"]),
    "execute_trade": (f"{VAULT_OWNER}-vault/execute_trade", ["trades:execute"]),
}
SINGLE_USE_TOOLS = {"execute_trade"}

ENFORCEMENT_MODE = os.environ.get("ENFORCEMENT_MODE", "gateway")

extensions = []
if ENFORCEMENT_MODE == "embedded":
    import uma_extension
    extensions.append(uma_extension.build(TOOLS, SINGLE_USE_TOOLS))

mcp = MCPServer(f"{VAULT_OWNER}-vault", extensions=extensions)

if ENFORCEMENT_MODE == "embedded":
    # A resource that protects itself also has to publish for itself.
    #
    # RFC 9728 puts the metadata at the resource's own origin, so when there
    # is no gateway in front of this process there is nowhere else for it to
    # come from. In gateway mode the ext_authz service serves these and this
    # block does not run — one implementation either way, from lib/.
    import uma_publish
    uma_publish.attach(mcp, TOOLS)


@mcp.tool()
def get_positions() -> dict:
    """The owner's current holdings summary: positions and allocation."""
    return {"as_of": FIXTURES["as_of"], "positions": FIXTURES["positions"]}


@mcp.tool()
def get_transactions(account: str = "brokerage-main") -> dict:
    """Transaction history and cost basis for one of Alice's accounts."""
    txns = [t for t in FIXTURES["transactions"] if t["account"] == account]
    return {"account": account, "transactions": txns}


@mcp.tool()
def execute_trade(symbol: str, side: str, quantity: int) -> dict:
    """Execute a trade in Alice's account. (Fixture execution — no market.)"""
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    return {
        "status": "executed",
        "order": {"symbol": symbol, "side": side, "quantity": quantity},
        "note": "fixture execution — no real market behind this endpoint",
    }


if __name__ == "__main__":
    # SDK 2.0 moved host/port from the constructor to run(), and defaults host
    # to 127.0.0.1 — which binds to nothing reachable from inside a container.
    mcp.run(transport="streamable-http", host="0.0.0.0", port=9020)
