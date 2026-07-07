"""alice-vault-mcp — Alice's brokerage vault as an MCP server.

Fixture data through a real protocol path: positions, transaction history,
and a pretend trade-execution endpoint, served over MCP streamable-http.
This server never speaks UMA or AAuth — protection is conferred by the
gateway in front of it (the whole point of primitive 5's transformation).
"""

import json
import pathlib

from mcp.server.fastmcp import FastMCP

FIXTURES = json.loads((pathlib.Path(__file__).parent / "fixtures.json").read_text())

mcp = FastMCP("alice-vault", host="0.0.0.0", port=9020)


@mcp.tool()
def get_positions() -> dict:
    """Alice's current holdings summary: positions and allocation (read-only)."""
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
    mcp.run(transport="streamable-http")
