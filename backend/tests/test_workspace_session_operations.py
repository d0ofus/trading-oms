from datetime import UTC, datetime

import pytest
from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.diagnostics import broker_diagnostic, exception_diagnostic
from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.graph import compile_graph, templates
from trading_oms_backend.workspace.sessions import execution_bounds, next_session_day
from trading_oms_backend.workspace.store import Conflict, Store


def test_broker_diagnostics_never_copy_free_form_response():
    result = broker_diagnostic(321, "Read-Only mode. arbitrary-secret-value")
    assert result["reason"] == "api_read_only"
    assert "arbitrary-secret-value" not in str(result)
    assert broker_diagnostic(321, "arbitrary-secret-value")["reason"] == "request_validation"


def test_callback_retains_only_allowlisted_read_only_reason(tmp_path):
    import queue

    from trading_oms_backend.workspace.broker import GatewayData

    observations = queue.Queue()
    adapter = GatewayData(observations)
    adapter.data_error(-1, 321, "Read-Only mode. arbitrary-secret-value")
    event = observations.get_nowait()
    assert event["diagnostic"]["reason"] == "api_read_only"
    assert "arbitrary-secret-value" not in str(event)
    subject = Engine(Store(tmp_path), BrokerDouble)
    subject.observe({**event, "epoch": subject.broker.epoch})
    notice = subject.incidents.get("broker_notice")
    assert "read-only" in notice["detail"]
    assert "arbitrary-secret-value" not in str(subject.store.events())


def test_exception_diagnostics_exclude_arguments_and_locals():
    try:
        raise RuntimeError("arbitrary-secret-value")
    except RuntimeError as exc:
        result = exception_diagnostic(exc, "subscribe")
    assert result["exception"] == "RuntimeError"
    assert result["frames"]
    assert "arbitrary-secret-value" not in str(result)


def test_engine_fault_does_not_drop_remaining_callbacks_in_its_batch(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    seen = []

    def observe(event):
        if event["type"] == "first":
            raise OSError("synthetic fault")
        seen.append(event["type"])

    engine.observe = observe
    engine.maintain = lambda: engine.stopping.set()
    for kind in ("first", "execution", "order"):
        engine.observations.put({"type": kind, "epoch": 1})
    engine._loop()
    assert seen == ["execution", "order"]
    assert engine.store.get("incident", "engine_fault")["diagnostic"]["observation"] == "first"


def test_data_connecting_is_not_a_persistent_critical_incident(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.observe({"type": "broker_error", "code": 2119, "request": -1})
    assert not engine.incidents.applicable()
    assert any(e["type"] == "broker.service.connecting" for e in engine.store.events())
    engine.observe({"type": "broker_error", "code": 2104, "request": -1})
    assert not engine.incidents.applicable()


def test_unused_run_removal_preserves_history_and_needs_no_broker(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.store.put("run", "r", {"id": "r", "armed": False, "position": "0", "state": "ready"})
    assert engine.remove_run("r")["archived"]
    assert engine.store.get("run", "r")
    assert any(e["type"] == "run.archived" for e in engine.store.events())


def test_removal_never_hides_a_position_or_uncertain_order(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.store.put("run", "r", {"id": "r", "armed": False, "position": "1"})
    with pytest.raises(Conflict):
        engine.remove_run("r")
    engine.store.put("run", "r", {"id": "r", "armed": False, "position": "0"})
    engine.store.reserve_order("o", {"quantity": 1}, "r", 100)
    with pytest.raises(Conflict):
        engine.remove_run("r")
    assert not engine.store.get("run", "r").get("archived")


def test_extended_schedule_is_broker_bounded_and_timezone_aware():
    contract = {"trading_hours": "20260917:0400-20260917:2000", "time_zone": "US/Eastern"}
    start, end = execution_bounds("2026-09-17", "extended", contract)
    assert (start.hour, end.hour) == (8, 0)
    assert end.day == 18
    assert execution_bounds("2026-09-19", "extended", contract) is None
    assert execution_bounds("2026-09-17", "extended", {}) is None
    assert next_session_day(datetime(2026, 9, 19, 12, tzinfo=UTC)) == "2026-09-21"


def test_schema_three_hash_and_settings_remain_unchanged():
    old = templates()[0]["document"]
    old["schema_version"] = 3
    old["settings"].pop("trading_hours", None)
    old["settings"].pop("stop_limit_offset", None)
    compiled = compile_graph(old)
    assert compiled.digest == "6d3b57ea51d653e938392d460678ef904e2e1ee271110c65bf4fec4efc6659dc"
    upgraded = {
        **old,
        "schema_version": 4,
        "settings": {**old["settings"], "trading_hours": "regular", "stop_limit_offset": "0.10"},
    }
    assert compile_graph(upgraded).digest != compiled.digest
    assert "trading_hours" not in compiled.document["settings"]
