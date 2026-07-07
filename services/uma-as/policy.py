"""Alice's tier policy — the owner-side configuration uma-as evaluates.

This is deliberately a small, legible document (not a policy language):
each tier names the resources it covers, the terms template the AS dictates
for them, and whether granting requires asking Alice. The portal edits it
through the owner API.
"""

import copy
import threading

_LOCK = threading.Lock()

# Default policy — the state Alice's "morning scene" produces.
_TIERS: dict[str, dict] = {
    "tier1": {
        "name": "Holdings summary",
        "resources": ["alice-vault/get_positions"],
        "ask_me": False,
        "terms": {
            "template_id": "alice/advisor-tier1/v2",
            "purpose": "Suitability review for advisory onboarding",
            "scope": ["positions:read"],
            "expires_in": 172800,
            "prohibited": [
                "retention-after-review",
                "marketing",
                "model-training",
            ],
        },
    },
    "tier2": {
        "name": "Transaction history and cost basis",
        "resources": ["alice-vault/get_transactions"],
        "ask_me": False,
        "terms": {
            "template_id": "alice/advisor-tier2/v2",
            "purpose": "Portfolio analysis for the current advisory engagement",
            "scope": ["transactions:read"],
            "expires_in": 86400,
            "prohibited": [
                "client-benchmarking",
                "sharing-outside-engagement-team",
                "retention-after-engagement",
            ],
            "constraints": {"accounts": ["brokerage-main"]},
        },
    },
    "tier3": {
        "name": "Trade execution",
        "resources": ["alice-vault/execute_trade"],
        "ask_me": True,
        "terms": {
            "template_id": "alice/advisor-tier3/v2",
            "purpose": "Execution of one client-approved order",
            "scope": ["trades:execute"],
            "expires_in": 900,
            "prohibited": [
                "orders-beyond-approved-parameters",
                "discretionary-reuse-of-authority",
            ],
            "per_operation": True,
        },
    },
}


def tiers() -> dict[str, dict]:
    with _LOCK:
        return copy.deepcopy(_TIERS)


def tier_for_resource(resource_id: str) -> tuple[str, dict] | tuple[None, None]:
    with _LOCK:
        for tid, t in _TIERS.items():
            if resource_id in t["resources"]:
                return tid, copy.deepcopy(t)
    return None, None


def update_tier(tier_id: str, patch: dict) -> dict:
    """Owner edits: terms fields and the ask_me switch. Resources are fixed
    by registration, not editable here."""
    with _LOCK:
        if tier_id not in _TIERS:
            raise KeyError(tier_id)
        tier = _TIERS[tier_id]
        if "ask_me" in patch:
            tier["ask_me"] = bool(patch["ask_me"])
        terms_patch = patch.get("terms", {})
        for field in ("purpose", "expires_in", "prohibited"):
            if field in terms_patch:
                tier["terms"][field] = terms_patch[field]
        # Any owner edit produces a new template version so contracts are
        # verifiably tied to the terms in force when they were signed.
        base = tier["terms"]["template_id"].rsplit("/v", 1)[0]
        version = int(tier["terms"]["template_id"].rsplit("/v", 1)[1]) + 1
        tier["terms"]["template_id"] = f"{base}/v{version}"
        return copy.deepcopy(tier)
