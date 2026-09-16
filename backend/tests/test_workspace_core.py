from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_oms_backend.workspace.graph import GraphError, compile_graph, templates
from trading_oms_backend.workspace.store import Conflict, Store


def test_layout_and_labels_do_not_change_execution_hash():
    document = templates()[0]["document"]
    changed = deepcopy(document)
    changed["nodes"][0]["position"] = {"x": 100, "y": 250}
    changed["nodes"][0]["label"] = "My source"
    assert compile_graph(document).digest == compile_graph(changed).digest


def test_rewiring_changes_executable_results():
    document = templates()[1]["document"]
    graph = compile_graph(document)
    values = {"close": Decimal("110"), "sma_fast": Decimal("105"), "sma_slow": Decimal("100")}
    result = graph.evaluate(values, {})
    assert result["stop"] < values["close"]
    assert result["exit"] is False
    changed = deepcopy(document)
    next(n for n in changed["nodes"] if n["id"] == "exit_rule")["params"]["op"] = "gt"
    assert compile_graph(changed).evaluate(values, {})["exit"] is True


def test_cycle_and_missing_protection_are_rejected():
    document = templates()[0]["document"]
    document["edges"].append({"source": "entry", "target": "entry_rule", "input": "a"})
    with pytest.raises(GraphError):
        compile_graph(document)
    document = templates()[0]["document"]
    document["nodes"] = [node for node in document["nodes"] if node["id"] != "stop"]
    with pytest.raises(GraphError):
        compile_graph(document)


def test_store_optimistic_concurrency_and_immutable_publication(tmp_path):
    store = Store(tmp_path)
    item = store.save_draft(None, "Breakout", templates()[0]["document"], 0)
    published = store.publish(item["id"], item["revision"])
    changed = deepcopy(item["document"])
    changed["nodes"][0]["position"] = {"x": 44, "y": 55}
    with pytest.raises(Conflict):
        store.save_draft(item["id"], "Conflict", changed, 0)
    store.save_draft(item["id"], "New draft", changed, store.get("draft", item["id"])["revision"])
    assert store.version(item["id"], published["version"])["name"] == "Breakout"


def test_emergency_state_survives_restart_and_events_are_append_only(tmp_path):
    store = Store(tmp_path)
    store.set_emergency(True)
    assert Store(tmp_path).emergency()
    with store.connect() as db, pytest.raises(Exception, match="append-only"):
        db.execute("DELETE FROM events")
    assert store.events()[0]["type"] == "emergency.activated"


def test_durable_outbox_never_retries_uncertain_dispatch(tmp_path):
    store = Store(tmp_path)
    payload = {"symbol": "AAPL", "quantity": 1, "limit": "100", "stop": "99"}
    store.put(
        "run",
        "replay",
        {"armed": True, "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )
    assert store.reserve_order(
        "test-intent", payload, "replay", 100, {"symbol": "AAPL", "risk": "1", "notional": "100"}
    )["created"]
    store.mark_dispatch("test-intent")
    duplicate = Store(tmp_path).reserve_order("test-intent", payload, "replay", 100)
    assert duplicate["created"] is False
    assert duplicate["state"] == "dispatching"
    with pytest.raises(Conflict):
        store.reserve_order("test-intent", {**payload, "quantity": 2}, "replay", 100)


def test_backup_restores_event_integrity(tmp_path):
    store = Store(tmp_path / "active")
    store.set_emergency(True)
    backup = store.backup(tmp_path / "backup")
    assert backup.exists()
    assert store.verify() == {"integrity": "ok", "events": 1}
