import json
from datetime import UTC, datetime, timedelta

from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.audit import audit_detail, audit_page, record_page
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Store


def test_recent_page_watermark_catchup_and_lazy_payload(tmp_path):
    store = Store(tmp_path)
    with store.transaction() as db:
        for i in range(450):
            store.append(db, "fixture", {"reason": str(i), "large": "x" * 2000})
    recent = audit_page(store)
    assert len(recent["items"]) == 200
    assert recent["items"][0]["sequence"] == 450
    assert "payload" not in recent["items"][0]
    assert len(json.dumps(recent)) < 50000
    older = audit_page(store, before=recent["next_cursor"], watermark=recent["watermark"])
    assert older["items"][0]["sequence"] == 250
    store.event("new", {})
    assert audit_page(store, after=recent["watermark"])["items"][0]["sequence"] == 451
    assert audit_detail(store, 1)["payload"]["large"] == "x" * 2000


def test_sparse_search_has_bounded_scan_and_no_missing_matches(tmp_path):
    store = Store(tmp_path)
    with store.transaction() as db:
        for i in range(4010):
            store.append(db, "fixture", {"reason": "needle" if i == 0 else "other"})
    first = audit_page(store, q="needle")
    assert not first["items"]
    assert first["scanned_through"] == 2011
    second = audit_page(store, q="needle", before=first["next_cursor"])
    last = audit_page(store, q="needle", before=second["next_cursor"])
    assert [e["sequence"] for e in last["items"]] == [1]


def test_search_continuation_works_both_directions_without_skipping_matches(tmp_path):
    store = Store(tmp_path)
    with store.transaction() as db:
        for i in range(4010):
            store.append(db, "fixture", {"reason": "needle" if i in (0, 4009) else "other"})
    forward = audit_page(store, q="needle", after=1)
    assert not forward["items"]
    assert forward["newer_cursor"] == 2001
    forward = audit_page(store, q="needle", after=forward["newer_cursor"])
    forward = audit_page(store, q="needle", after=forward["newer_cursor"])
    assert [e["sequence"] for e in forward["items"]] == [4010]
    previous = audit_page(store, q="needle", before=forward["older_cursor"])
    assert not previous["items"]
    previous = audit_page(store, q="needle", before=previous["older_cursor"])
    previous = audit_page(store, q="needle", before=previous["older_cursor"])
    assert [e["sequence"] for e in previous["items"]] == [1]


def test_compact_reads_never_construct_candles_and_records_are_paged(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine._display_candles = lambda *_: (_ for _ in ()).throw(AssertionError("eager candles"))
    for i in range(250):
        engine.store.put("run", str(i), {"id": str(i), "armed": False, "position": "0"})
    assert len(engine.overview()["runs"]) <= 50
    assert len(record_page(engine.store, "runs")["items"]) == 100


def test_candle_pages_retain_older_history_with_realtime_bars_and_share_cache(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.data[1] = {"conid": 1}
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=300)
    bars = {
        i: {
            "timestamp": int((start + timedelta(minutes=i)).timestamp()),
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "10",
        }
        for i in range(250)
    }
    engine.history_bars[1] = {60: bars, 5: {}}
    engine.display_bars[1] = {
        9999: {**bars[249], "timestamp": bars[249]["timestamp"] + 60, "type": "realtime_bar"}
    }
    page = engine.candles(1)
    assert len(page["items"]) == 120
    assert engine.candles(1) is page
    older = engine.candles(1, before=page["next_cursor"])
    assert len(older["items"]) == 120
    assert older["items"][-1]["timestamp"] < page["items"][0]["timestamp"]
    assert all(row["source"] == "history" for row in older["items"])
    assert all(row["complete"] for row in older["items"])


def test_legacy_evidence_pages_do_not_eagerly_load_payloads(tmp_path):
    from trading_oms_backend.workspace.audit import legacy_page
    from trading_oms_backend.workspace.legacy import import_history

    store = Store(tmp_path)
    original = [
        {
            "sequence": i + 1,
            "type": "historical.fixture",
            "timestamp": "2026-09-21T00:00:00+00:00",
            "payload": {"evidence": "x" * 1000},
        }
        for i in range(250)
    ]
    imported = import_history(store, "Synthetic historical evidence", original)
    first = legacy_page(store, imported["id"])
    assert len(first["items"]) == 200
    assert "payload" not in first["items"][0]
    second = legacy_page(store, imported["id"], first["next_cursor"])
    assert len(second["items"]) == 50
    assert second["items"][0]["sequence"] == 201
    assert (
        store.get("legacy_record", imported["id"] + ":201")["payload"] == original[200]["payload"]
    )
