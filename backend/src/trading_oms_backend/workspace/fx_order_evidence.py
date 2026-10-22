"""FX quantity provenance. Reported callbacks remain unchanged in the journal."""

import json
from decimal import Decimal

from .fx_ledger import executions
from .graph import number
from .store import now

IDENTITY = (
    "broker_id",
    "client_id",
    "own_account",
    "conid",
    "reference",
    "permanent_id",
    "sec_type",
    "currency",
    "routing_exchange",
    "action",
    "order_type",
    "tif",
)


def ensure_backup(store):
    if not store.get("migration", "fx_protection_evidence_v1"):
        store.backup(store.directory / "backups")
        store.put("migration", "fx_protection_evidence_v1", {"backed_up_at": now()})


def audited_update(store, kind, order_id, value, event_type):
    with store.transaction() as db:
        if store.read(db, kind, order_id) == value:
            return
        store.write(db, kind, order_id, value)
        store.append(db, event_type, {"order_id": order_id, **value})


def record(store, event, projected):
    intent = next((o for o in store.orders() if o["broker_id"] == event["broker_id"]), None)
    if not intent or intent["payload"].get("execution") != "fx_breakout":
        return
    ensure_backup(store)
    if accepted_observation(event):
        proof = {k: event.get(k) for k in (*IDENTITY, "quantity", "status")}
        previous = store.get("fx_accepted_order", intent["id"]) or {}
        proof["quantity_conflict"] = bool(previous.get("quantity_conflict")) or bool(
            previous and number(previous["quantity"]) != number(proof["quantity"])
        )
        if previous != proof:
            audited_update(
                store, "fx_accepted_order", intent["id"], proof, "fx.order.accepted_quantity"
            )
    evidence = quantity_evidence(store, intent, projected)
    projected["quantity_evidence"] = evidence
    if evidence["basis"] == "accepted_quantity_and_executions":
        audited_update(
            store, "fx_quantity_correction", intent["id"], evidence, "fx.order.quantity_verified"
        )


def accepted_observation(observed):
    return bool(
        observed.get("status") in {"Submitted", "PreSubmitted", "Filled"}
        and not observed.get("completed")
        and not observed.get("status_conflict")
        and observed.get("own_account") is True
        and all(observed.get(k) is not None for k in IDENTITY)
        and observed.get("permanent_id")
        and number(observed.get("quantity", 0)) > 0
    )


def accepted_evidence(store, intent):
    evidence = store.get("fx_accepted_order", intent["id"])
    if evidence:
        return evidence
    # Legacy projections may already contain the zero total. Only an actual
    # accepted callback in the immutable journal can supply the missing proof.
    with store.connect() as db:
        rows = db.execute(
            "SELECT payload FROM events WHERE type='broker.order.observed' "
            "AND json_extract(payload,'$.reference')=? "
            "AND json_extract(payload,'$.status') IN ('Submitted','PreSubmitted','Filled') "
            "ORDER BY sequence DESC LIMIT 100",
            ("oms-" + intent["id"],),
        ).fetchall()
    candidates = [json.loads(row[0]) for row in rows]
    accepted = [e for e in candidates if accepted_observation(e)]
    if not accepted:
        return {}
    return {
        **accepted[0],
        "quantity_conflict": len({number(e["quantity"]) for e in accepted}) != 1,
    }


def quantity_evidence(store, intent, observed):
    reported = observed.get("quantity")
    result = {"reported": reported, "effective": reported, "basis": "broker_reported"}
    if reported is None or number(reported) != 0:
        return result
    result.update(effective=None, basis="unverified_zero_total")
    if (
        not observed.get("completed")
        or observed.get("status") != "Filled"
        or observed.get("status_conflict")
    ):
        return result
    accepted = accepted_evidence(store, intent)
    if not accepted or any(observed.get(k) != accepted.get(k) for k in IDENTITY):
        return result
    if accepted.get("quantity_conflict"):
        return result
    fills = [event for order, event in executions(store) if order["id"] == intent["id"]]
    if not fills or any(
        e.get("own_account") is not True
        or e.get("client_id") != observed["client_id"]
        or e.get("conid") != observed["conid"]
        or e.get("side") != ("BOT" if observed["action"] == "BUY" else "SLD")
        for e in fills
    ):
        return result
    total = sum((number(e["quantity"]) for e in fills), Decimal(0))
    if (
        total == number(accepted["quantity"]) == number(observed.get("filled", -1))
        and number(observed.get("remaining", 0)) == 0
    ):
        result.update(effective=str(total), basis="accepted_quantity_and_executions")
    return result
