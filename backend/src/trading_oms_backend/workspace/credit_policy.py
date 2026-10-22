"""Additive broker credit terms. Published strategy semantics remain unchanged."""

from .graph import digest
from .store import Conflict

POLICY = "broker_credit_v1"
BUYING_POWER_POLICY = "paper_buying_power_v1"
CURRENT_POLICY = BUYING_POWER_POLICY
QUIET_POLICY = "quiet_fx_v1"

CREDIT_DETAILS = {
    "insufficient_funds": "Broker credit preview: insufficient funds or margin for this order.",
    "permissions": "Broker credit preview: account eligibility or permission restriction.",
    "unsupported_parameters": "Broker credit preview: unsupported order structure or quantity.",
    "unavailable_capability": "Broker credit preview: funding unavailable for this account.",
    "acknowledgment_required": "Broker credit preview requires an account acknowledgment in TWS.",
    "minimum_size": "Broker credit preview reports a quantity below the permitted minimum.",
    "unknown": "Broker credit preview rejected or could not verify this order.",
}


def credit_category(message, advanced=""):
    from .rejections import classify_order_rejection

    category = classify_order_rejection(message, advanced)["category"]
    if category == "unknown" and isinstance(message, str) and len(message) <= 4096:
        if "insufficient margin" in message.lower():
            category = "insufficient_funds"
    return category


def bind_credit(plan, policy):
    if policy is None:
        return plan
    if policy not in {POLICY, BUYING_POWER_POLICY}:
        raise Conflict("Unsupported broker funding policy.")
    if plan is None:
        return None
    plan = {**plan, "funding_policy": policy}
    if plan.get("family") == "spot_fx":
        plan["authorization_policy"] = QUIET_POLICY
    plan["hash"] = digest({k: v for k, v in plan.items() if k != "hash"})
    return plan


def broker_credit(plan):
    return plan.get("funding_policy") in {POLICY, BUYING_POWER_POLICY}


def buying_power_policy(plan):
    return plan.get("funding_policy") == BUYING_POWER_POLICY


def ensure_policy(store, policy=POLICY):
    if policy not in {POLICY, BUYING_POWER_POLICY}:
        raise Conflict("Unsupported broker funding policy.")
    if store.get("funding_policy", policy):
        return
    store.backup(store.directory / "backups")
    with store.transaction() as db:
        if not store.read(db, "funding_policy", policy):
            store.write(
                db,
                "funding_policy",
                policy,
                {
                    "revision": 1,
                    "paper_only": True,
                    "quiet_fx": QUIET_POLICY,
                    "preview_interval_seconds": 60,
                    "evidence_seconds": 30,
                    "paired_evidence_seconds": 180,
                    "mandatory_preview": policy == POLICY,
                    "capacity_basis": "broker_buying_power"
                    if policy == BUYING_POWER_POLICY
                    else "credit",
                },
            )
            store.append(db, "funding.policy.installed", {"policy": policy, "backup_created": True})
