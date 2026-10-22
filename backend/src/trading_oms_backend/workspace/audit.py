"""Bounded read-only audit projections. The immutable ledger remains authoritative."""

import json


def summary(row):
    payload = json.loads(row["payload"])
    return {
        "sequence": row["sequence"],
        "timestamp": row["timestamp"],
        "type": row["type"],
        "summary": str(
            payload.get(
                "reason", payload.get("detail", payload.get("name", "Recorded in event ledger"))
            )
        )[:500],
    }


def audit_page(store, *, before=None, after=None, q="", limit=200, watermark=None):
    if len(q) > 200 or not 1 <= limit <= 200:
        raise ValueError("Use at most 200 characters and 200 records per audit page.")
    with store.connect() as db:
        latest = db.execute("SELECT COALESCE(MAX(sequence),0) FROM events").fetchone()[0]
        watermark = min(latest, max(0, watermark)) if watermark is not None else latest
        ascending = after is not None
        cursor = max(0, after or 0) if ascending else min(before or watermark + 1, watermark + 1)
        operator, direction = (">", "ASC") if ascending else ("<", "DESC")
        rows = db.execute(
            f"SELECT sequence,timestamp,type,payload FROM events WHERE sequence{operator}? "
            f"AND sequence<=? ORDER BY sequence {direction} LIMIT ?",
            (cursor, watermark, 2000 if q else limit),
        ).fetchall()
    items, scanned = [], cursor
    for row in rows:
        scanned = row["sequence"]
        if not q or q.casefold() in (row["type"] + " " + row["payload"]).casefold():
            items.append(summary(row))
        if len(items) == limit:
            break
    more = bool(rows) and (scanned < watermark if ascending else scanned > 1)
    return {
        "items": items,
        "watermark": watermark,
        "latest": latest,
        "next_cursor": scanned if more else None,
        "scanned_through": scanned,
        "older_cursor": (cursor + 1 if cursor > 0 else None)
        if ascending
        else (scanned if more else None),
        "newer_cursor": (scanned if more else None)
        if ascending
        else (cursor - 1 if cursor <= watermark else None),
    }


def audit_detail(store, sequence):
    with store.connect() as db:
        row = db.execute("SELECT * FROM events WHERE sequence=?", (sequence,)).fetchone()
    if row is None:
        raise ValueError("Audit event not found.")
    return {**dict(row), "payload": json.loads(row["payload"])}


def record_page(store, kind, before=None, limit=100):
    if kind not in {"runs", "orders"} or not 1 <= limit <= 200:
        raise ValueError("Choose runs or orders, with up to 200 records.")
    table = "documents" if kind == "runs" else "outbox"
    with store.connect() as db:
        where = "kind='run' AND " if kind == "runs" else ""
        rows = db.execute(
            f"SELECT rowid AS cursor,* FROM {table} WHERE {where}rowid<? "
            "ORDER BY rowid DESC LIMIT ?",
            (before if before is not None else 9223372036854775807, limit + 1),
        ).fetchall()
    items = []
    for row in rows[:limit]:
        value = json.loads(row["payload"])
        items.append(value if kind == "runs" else {**dict(row), "payload": value})
    return {"items": items, "next_cursor": rows[limit - 1]["cursor"] if len(rows) > limit else None}


def legacy_page(store, identity, after=0):
    with store.connect() as db:
        rows = db.execute(
            "SELECT rowid AS cursor,payload FROM documents WHERE kind='legacy_record' "
            "AND id LIKE ? AND rowid>? ORDER BY rowid LIMIT 201",
            (identity + ":%", max(0, after)),
        ).fetchall()
    items = []
    for row in rows[:200]:
        value = json.loads(row["payload"])
        items.append({k: value[k] for k in ("sequence", "timestamp", "type")})
    return {"items": items, "next_cursor": rows[199]["cursor"] if len(rows) > 200 else None}
