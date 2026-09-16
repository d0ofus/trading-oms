"""Real paper-session evidence, followed by explicit operator review."""

from datetime import UTC, datetime

from .market import calendar, session_bounds
from .store import Conflict, now


def observe_session(engine, stamp=None):
    stamp = stamp or datetime.now(UTC)
    bounds = session_bounds(stamp)
    if not bounds:
        return
    opened, closed = bounds
    day = opened.date().isoformat()
    runs = [
        r for r in engine.store.list("run") if r.get("session_date") == day and r.get("unattended")
    ]
    if not runs:
        return
    record = engine.store.get("paper_session", day) or {
        "date": day,
        "started_at": stamp.isoformat(),
        "process": engine.process_identity,
        "continuous": True,
        "accepted": False,
        "eligible": False,
        "runs": 0,
    }
    if record.get("ended_at"):
        return
    record["continuous"] = record["continuous"] and record["process"] == engine.process_identity
    record["runs"] = max(record["runs"], len(runs))
    record["last_observed_at"] = stamp.isoformat()
    if stamp >= closed and engine.reconciled:
        flat = all(p["quantity"] == 0 for p in engine.owned().values())
        terminal = all(
            o["state"] in {"filled", "cancelled", "rejected"} for o in engine.store.orders()
        )
        healthy = not any(not i.get("resolved") for i in engine.store.list("incident"))
        record.update(
            ended_at=stamp.isoformat(),
            eligible=flat
            and terminal
            and healthy
            and record["continuous"]
            and not engine.store.emergency(),
            flat=flat,
            orders_terminal=terminal,
            incidents_resolved=healthy,
        )
        engine.store.event("paper_session.completed", record)
    engine.store.put("paper_session", day, record)


def accept_session(store, day, confirmed):
    record = store.get("paper_session", day)
    if confirmed is not True or not record or not record.get("eligible"):
        raise Conflict("A completed, reconciled real paper session must be eligible for review.")
    record.update(accepted=True, accepted_at=now())
    store.put("paper_session", day, record)
    store.event(
        "paper_session.operator_accepted",
        {"date": day, "statement": "No unresolved P0/P1 defects or unexplained orders/positions."},
    )
    return record


def session_status(store):
    records = sorted(store.list("paper_session"), key=lambda r: r["date"])
    consecutive = 0
    previous = None
    for record in records:
        if not record.get("accepted"):
            consecutive, previous = 0, None
            continue
        adjacent = (
            previous is not None
            and calendar().next_session(previous).date().isoformat() == record["date"]
        )
        consecutive = consecutive + 1 if adjacent else 1
        previous = record["date"]
    return {
        "sessions": records,
        "consecutive_accepted": consecutive,
        "five_session_gate": consecutive >= 5,
    }
