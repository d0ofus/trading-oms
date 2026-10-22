from test_workspace_automatic_recovery import advance
from test_workspace_incidents import recovered_engine


def retired_fixture(tmp_path, monkeypatch):
    engine, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    engine.store.put("subscription", "12", {"conid": 12, "active": False})
    engine.store.put(
        "run",
        "paused",
        {
            "id": "paused",
            "conid": 12,
            "state": "paused",
            "position": 0,
            "armed": False,
            "archived": False,
        },
    )
    item = engine.incidents.raise_incident("history_feed_failure", "Old history", "old", conid=12)
    engine.reconciliation_evidence["started_sequence"] = engine.incidents.watermark()
    return engine, item, clock


def test_paused_flat_run_retires_unused_feed_without_stability_wait(tmp_path, monkeypatch):
    engine, item, _ = retired_fixture(tmp_path, monkeypatch)
    engine.refresh_incidents()
    result = engine.incidents.get(item["id"])
    assert result["restriction"] == "released"
    assert result["release_kind"] == "dependency_retired"
    assert result["release_evidence"]["healthy_seconds"] == 0
    assert engine.store.get("run", "paused")["state"] == "paused"


def test_virtual_fx_pair_is_not_a_history_dependency(tmp_path, monkeypatch):
    engine, item, _ = retired_fixture(tmp_path, monkeypatch)
    engine.positions[12] = {"conid": 12, "sec_type": "CASH", "quantity": "8600"}
    engine.refresh_incidents()
    assert engine.incidents.get(item["id"])["restriction"] == "released"


def test_real_stock_exposure_retains_dependency(tmp_path, monkeypatch):
    engine, item, clock = retired_fixture(tmp_path, monkeypatch)
    engine.positions[12] = {"conid": 12, "sec_type": "STK", "quantity": "200"}
    advance(engine, clock)
    assert engine.incidents.get(item["id"])["restriction"] == "held"
    assert 12 in engine._data_dependencies()["contracts"]


def test_retirement_requires_current_completed_reconciliation_not_a_feed_timer(
    tmp_path, monkeypatch
):
    engine, item, _ = retired_fixture(tmp_path, monkeypatch)
    engine.reconciliation_evidence["instance"] = "previous-engine"
    engine.refresh_incidents()
    assert engine.incidents.get(item["id"])["restriction"] == "held"
    engine.reconciliation_evidence["instance"] = engine.process_identity
    engine.reconciliation_evidence["started_sequence"] = 0
    engine.refresh_incidents()
    assert engine.incidents.get(item["id"])["restriction"] == "released"


def test_real_fx_allocation_retains_history_dependency(tmp_path, monkeypatch):
    engine, item, clock = retired_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        engine, "owned", lambda: {"paused": {"run_id": "paused", "conid": 12, "quantity": "200"}}
    )
    advance(engine, clock)
    assert engine.incidents.get(item["id"])["restriction"] == "held"


def test_only_complete_known_fault_episode_recovers_automatically(tmp_path, monkeypatch):
    engine, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    engine.code_verified = True
    known = {"fingerprint": "6120a896001cbf3769738e4a"}
    item = engine.incidents.raise_incident("engine_fault", "Request fault", "old", diagnostic=known)
    advance(engine, clock)
    assert engine.incidents.get(item["id"])["release_kind"] == "corrected_data_fault"
    item = engine.incidents.raise_incident("engine_fault", "Request fault", "old", diagnostic=known)
    engine.incidents.raise_incident("engine_fault", "Unknown fault", "old")
    advance(engine, clock)
    assert engine.incidents.get(item["id"])["restriction"] == "ready_for_release"


def test_repeated_known_fault_without_progress_is_one_failure(tmp_path, monkeypatch):
    engine, _, _ = recovered_engine(tmp_path, monkeypatch, automatic=True)
    diagnostic = {"fingerprint": "6120a896001cbf3769738e4a"}
    first = engine.incident("engine_fault", "Request fault", diagnostic=diagnostic)
    second = engine.incident("engine_fault", "Request fault", diagnostic=diagnostic)
    assert second["id"] == first["id"]
    assert second["occurrences"] == 1
    engine.last_loop += 1
    third = engine.incident("engine_fault", "Request fault", diagnostic=diagnostic)
    assert third["occurrences"] == 2
