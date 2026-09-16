"""Read-only historical evidence and reviewed migration of supported replay definitions."""

import re

from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.strategy_dsl import parse_strategy_dsl

from .graph import DEFAULT_SETTINGS, SPECS, digest
from .store import now


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if re.search(
                r"account|secret|token|password|credential|chat_id|private_key|certificate",
                key,
                re.I,
            )
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if re.search(
            r"\b(?:DU|U)[0-9]{5,}\b|https?://|\bgh[pousr]_\w{20,}|\bsk-[\w-]{20,}|\d{5,15}:[\w-]{20,}",
            value,
        ):
            return "[redacted historical value]"
    return value


def import_history(store, name, records):
    if not 1 <= len(records) <= 10000:
        raise ValueError("Import 1–10,000 historical journal records at a time.")
    validated = [JournalRecord.from_json_dict(record).to_json_dict() for record in records]
    if any(b["sequence"] <= a["sequence"] for a, b in zip(validated, validated[1:], strict=False)):
        raise ValueError("Historical journal records must have increasing sequence numbers.")
    identity = digest(validated)
    prior = store.get("legacy_import", identity)
    if prior:
        return prior
    record = {
        "id": identity,
        "name": name,
        "kind": "journal",
        "records": len(validated),
        "imported_at": now(),
        "read_only": True,
        "paper_authorization": False,
    }
    with store.transaction() as db:
        for item in validated:
            store.write(
                db,
                "legacy_record",
                f"{identity}:{item['sequence']}",
                {**redact(item), "import_id": identity},
            )
        store.write(db, "legacy_import", identity, record)
        store.append(db, "legacy.imported", record)
    return record


def migrate_definition(store, name, raw):
    old = parse_strategy_dsl(raw)
    if old.bar_timeframe_seconds not in {5, 60, 300}:
        raise ValueError("This historical candle interval is not supported by the paper workspace.")
    settings = {
        **DEFAULT_SETTINGS,
        "symbol": old.symbol,
        "timeframe": old.bar_timeframe_seconds,
        "evaluation": "bar_close",
    }

    def node(identity, kind, **parameters):
        return {
            "id": identity,
            "kind": kind,
            "label": SPECS[kind]["label"],
            "params": {**SPECS[kind]["defaults"], **parameters},
        }

    document = {
        "schema_version": 3,
        "settings": settings,
        "nodes": [
            node("price", "field", field="close", source="closed"),
            node(
                "average",
                "field",
                field="sma",
                source="closed",
                period=old.parameters.lookback_bars,
            ),
            node("condition", "compare", op="gt"),
            node("entry", "entry"),
            node("stop", "stop"),
        ],
        "edges": [
            {"source": "price", "target": "condition", "input": "a"},
            {"source": "average", "target": "condition", "input": "b"},
            {"source": "condition", "target": "entry", "input": "a"},
        ],
    }
    draft = store.save_draft(None, name, document, 0)
    store.event(
        "legacy.definition.migrated",
        {
            "source_hash": digest(raw),
            "draft_id": draft["id"],
            "protection_review_required": True,
            "paper_authorization": False,
        },
    )
    return draft
