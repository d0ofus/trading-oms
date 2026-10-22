"""One read-only assessment of current FX protection evidence."""

from .fx_data import recent
from .graph import number
from .store import now


def assess(engine, run, position):
    result = {
        "state": "checking",
        "reasons": [],
        "evaluated_at": now(),
        "evidence_revision": getattr(engine, "_evidence_revision", 0),
        "broker_status": None,
    }

    def outcome(state, reason=None):
        return {**result, "state": state, "reasons": [reason] if reason else []}

    quantity = number(position.get("quantity", 0))
    if not quantity:
        return outcome("closed")
    request = engine.store.get("exit_request", run["id"]) or {}
    if request.get("requested_at"):
        return outcome("exit_pending", "Exit in progress; competing sells remain serialized.")
    state = engine.store.get("fx_protection", run["id"]) or {}
    if not engine.connected or not engine.attested or not engine._fx_account_ready(run):
        return outcome("checking", "Waiting for current paper-account and order evidence.")
    if not engine._fx_ownership_agrees(run):
        currency = run["binding"]["execution_plan"]["base_currency"]
        balance = engine.currency_facts.get(("CashBalance", currency), {})
        if balance and recent(balance.get("received_at"), 30):
            return outcome(
                "mismatch",
                "Current real currency balance does not establish the run's owned allocation.",
            )
        return outcome("checking", "Reconciling run-owned currency against current balances.")
    if run["protection_type"] == "locally_monitored":
        active = (
            number(state.get("quantity", 0)) == quantity
            and engine.data.get(run["conid"], {}).get("live")
            and engine._fx_quote_evaluation(run["conid"])["fresh"]
        )
        return outcome(
            "active" if active else "checking",
            None if active else "Waiting for fresh local-stop inputs.",
        )
    active = engine._fx_active_sells(run)
    if not active:
        return outcome("missing", "No active broker stop covers the owned quantity.")
    if len(active) != 1 or active[0]["payload"]["purpose"] != "protection":
        return outcome("mismatch", "Competing or unresolved sell orders require reconciliation.")
    order = active[0]
    observed = engine.broker_orders.get(order["broker_id"], {})
    result.update(
        order_id=order["id"], broker_status=observed.get("status"), stop=state.get("stop")
    )
    cancellation = engine.store.get("cancel_request", str(order["broker_id"])) or {}
    if (engine._fx_warning_view(order) or {}).get("state") == "awaiting_confirmation":
        return outcome(
            "checking", "Broker message 399: waiting for authoritative stop confirmation."
        )
    if order["state"] in {"cancel_pending", "unknown"} or cancellation.get("state") in {
        "queued",
        "pending",
    }:
        return outcome("mismatch", "Protection cancellation or outcome remains unresolved.")
    if observed.get("status_conflict"):
        return outcome("mismatch", "Conflicting broker protection statuses require reconciliation.")
    if observed.get("status") not in {"Submitted", "PreSubmitted"}:
        return outcome("checking", "Waiting for broker stop acceptance.")
    issues = engine._fx_identity(order, observed)
    if issues:
        return outcome("checking" if issues[0].startswith("Awaiting") else "mismatch", issues[0])
    # Completed callbacks and intents cannot supply working-order remaining quantity.
    if observed.get("remaining") is None:
        return outcome("checking", "Waiting for broker remaining stop quantity.")
    if number(observed["remaining"]) != quantity or number(
        order["payload"].get("stop", 0)
    ) != number(state.get("stop", 0)):
        return outcome(
            "mismatch", "Broker stop price or remaining quantity does not match owned exposure."
        )
    return outcome("active")
