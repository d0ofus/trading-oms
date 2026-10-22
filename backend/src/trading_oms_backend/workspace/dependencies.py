"""Pure current-operation dependency rules shared by data and presentation."""

from .graph import number

TERMINAL_OPERATIONS = {"closed", "completed", "cancelled", "confirmed", "rejected", "retired"}


def operation_active(kind, operation):
    if not operation or operation.get("state") in TERMINAL_OPERATIONS:
        return False
    if kind in {"exit_request", "incident_cancel"}:
        return bool(
            operation.get("state")
            or operation.get("run_id")
            or operation.get("requested_at")
            or operation.get("reason")
        )
    return bool(number(operation.get("quantity", 0)))


def never_submitted(db, order):
    """Require a durable positive local cancellation decision, not broker silence."""
    if order["state"] != "cancelled":
        return False
    key = order["id"]
    from .protection import order_ids

    if any(
        db.execute(
            "SELECT 1 FROM documents WHERE kind='broker_order' AND id=?", (str(i),)
        ).fetchone()
        for i in order_ids(order)
    ):
        return False
    blocked = db.execute(
        "SELECT 1 FROM events WHERE type='order.dispatch.blocked' "
        "AND json_extract(payload,'$.id')=? "
        "AND json_extract(payload,'$.never_submitted')=1 LIMIT 1",
        (key,),
    ).fetchone()
    dispatched = db.execute(
        "SELECT 1 FROM events WHERE type='order.dispatch.started' "
        "AND json_extract(payload,'$.id')=? LIMIT 1",
        (key,),
    ).fetchone()
    return bool(blocked and not dispatched)


def dependency(code, detail, run=None, **extra):
    return {
        "code": code,
        "detail": detail,
        "run_id": run.get("id") if run else None,
        "run_name": run.get("name", run.get("id")) if run else None,
        "remediation": "Inspect the affected run." if run else "Inspect account reconciliation.",
        "action": "desk" if run else "activity",
        **extra,
    }
