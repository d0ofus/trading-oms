import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta

import pytest
from test_workspace_engine import BrokerDouble
from test_workspace_health import healthy_watchdog

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.incidents import IncidentBook, safe_fault
from trading_oms_backend.workspace.store import Conflict, Store, now


def test_migration_backs_up_and_preserves_legacy_evidence(tmp_path):
    store = Store(tmp_path)
    legacy = {"id": "engine_fault", "resolved": False, "timestamp": now(), "detail": "Old fault"}
    store.put("incident", "engine_fault", legacy)
    store.event("incident.raised", legacy)
    original = store.events()[0]
    book = IncidentBook(store)
    episode = book.open()[0]
    assert episode["condition"] == "unknown"
    assert episode["scope"] == {"type": "workspace", "key": "*"}
    assert episode["investigation"] == "open"
    assert store.events()[0] == original
    backup = next((tmp_path / "backups").glob("incident-migration-*.sqlite3"))
    with sqlite3.connect(backup) as db:
        assert (
            json.loads(
                db.execute("SELECT payload FROM documents WHERE kind='incident'").fetchone()[0]
            )
            == legacy
        )
    IncidentBook(store)
    assert len(book.open()) == 1


def test_scoped_holds_follow_contract_and_do_not_depend_on_run_creation_time(tmp_path):
    store = Store(tmp_path)
    book = IncidentBook(store)
    btc = {"id": "btc", "conid": 1, "armed": True, "position": "0"}
    eth = {"id": "eth", "conid": 2, "armed": True, "position": "0"}
    for run in [btc, eth]:
        store.put("run", run["id"], run)
    book.raise_incident("market_data_failure", "Contract feed failed", "engine", conid=1)
    assert book.applicable([btc])
    assert not book.applicable([eth])
    assert not store.get("run", "btc")["armed"]
    assert store.get("run", "eth")["armed"]
    assert book.applicable([{**btc, "id": "new-run"}])
    book.raise_incident("unknown_failure", "Unknown scope", "engine", conid=2)
    assert book.applicable([btc]) and book.applicable([eth])


def test_migration_backs_up_existing_evidence_even_without_legacy_incidents(tmp_path):
    store = Store(tmp_path)
    store.event("fixture.evidence", {"preserve": True})
    original = store.events()[0]
    book = IncidentBook(store)
    assert not book.open()
    assert list((tmp_path / "backups").glob("incident-migration-*.sqlite3"))
    assert store.events()[0] == original


def test_restriction_revokes_authorizations_without_rewriting_inactive_saved_runs(tmp_path):
    store = Store(tmp_path)
    book = IncidentBook(store)
    for i in range(30):
        store.put("run", str(i), {"id": str(i), "armed": i == 0, "position": "0.000"})
    book.raise_incident("watchdog", "Fixture health failure", "engine")
    assert not store.get("run", "0")["armed"]
    assert store.get("run", "0")["state"] == "paused"
    assert store.list("incident_cancel") == [{"run_id": "0"}]
    assert len([e for e in store.events() if e["type"] == "run.disarmed"]) == 1


def test_repeated_faults_keep_an_episode_and_release_then_recur_creates_new_one(tmp_path):
    book = IncidentBook(Store(tmp_path))
    first = book.raise_incident("watchdog", "Lost health", "engine")
    second = book.raise_incident("watchdog", "Lost health", "engine")
    assert first["id"] == second["id"]
    assert second["occurrences"] == 1 and second["revision"] == first["revision"]
    with book.store.transaction() as db:
        book.recover_in(db, second, {"fixture": True})
    ready = book.open()[0]
    with book.store.transaction() as db:
        book.release_in(db, ready["id"], ready["revision"], "operator-fixture", "Verified recovery")
    assert not book.applicable([{"id": "new"}])
    third = book.raise_incident("watchdog", "Lost health", "engine")
    assert third["id"] != first["id"] and third["previous_episode"] == first["id"]
    assert book.page(view="history")["items"][0]["restriction"] == "released"


def test_release_is_revision_checked_and_never_overrides_active_condition(tmp_path):
    book = IncidentBook(Store(tmp_path))
    item = book.raise_incident("watchdog", "Fault", "engine")
    with pytest.raises(Conflict):
        with book.store.transaction() as db:
            book.release_in(db, item["id"], item["revision"], "operator", "Reviewed")
    with book.store.transaction() as db:
        book.recover_in(db, item, {"fixture": True})
    ready = book.open()[0]
    book.raise_incident("watchdog", "Recurrence", "engine")
    with pytest.raises(Conflict):
        with book.store.transaction() as db:
            book.release_in(db, ready["id"], ready["revision"], "operator", "Reviewed")


def test_diagnostics_never_include_exception_values_or_local_variables():
    private_value = "fixture-sensitive-value-not-for-journal"
    try:
        raise RuntimeError(private_value)
    except RuntimeError as exc:
        diagnostic = safe_fault(exc, "broker_observation", "tick")
    serialized = json.dumps(diagnostic)
    assert private_value not in serialized
    assert diagnostic["exception_class"] == "RuntimeError"
    assert len(diagnostic["frames"]) <= 8
    assert "locals" not in serialized


def test_recovery_reconciliation_identity_is_traceable_in_immutable_events(tmp_path):
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.connected = True
    engine.broker.reconcile = lambda: None
    engine.begin_reconcile()
    for tag, value in {
        "NetLiquidation": "10000",
        "AvailableFunds": "10000",
        "GrossPositionValue": "0",
    }.items():
        engine.observe({"type": "account_fact", "tag": tag, "value": value, "currency": "USD"})
    engine._finish_reconcile()
    events = engine.store.events()
    started = next(e["payload"] for e in events if e["type"] == "reconciliation.started")
    finished = next(e["payload"] for e in events if e["type"] == "reconciliation.finished")
    assert started["id"] == engine.reconciliation_evidence["id"]
    assert finished["recovery_evidence"] == engine.reconciliation_evidence
    assert finished["ready"]


def recovered_engine(tmp_path, monkeypatch, code="watchdog", *, automatic=False):
    # The older tests exercise the retained explicit-review rollback policy.
    monkeypatch.setenv("OMS_DISABLE_AUTOMATIC_RECOVERY", "0" if automatic else "1")
    clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    engine = Engine(Store(tmp_path), BrokerDouble)
    engine.connected = engine.attested = engine.reconciled = engine.clock_ok = True
    healthy_watchdog(engine)
    engine.incident(code, "Fixture interruption")
    item = engine.incidents.open()[0]
    engine.reconciliation_evidence = {
        "id": "complete-fixture",
        "instance": engine.process_identity,
        "epoch": engine.broker.epoch,
        "started_at": now(),
        "completed_at": now(),
        "started_sequence": engine.incidents.watermark(),
        "ready": True,
    }
    engine.reconciled_at = clock[0]
    engine.refresh_incidents()
    for _ in range(7):
        clock[0] += 5
        engine.last_loop = engine.reconciled_at = clock[0]
        healthy_watchdog(engine)
        engine.refresh_incidents()
    return engine, item, clock


def test_watchdog_requires_stability_and_post_failure_reconciliation(tmp_path, monkeypatch):
    engine, item, clock = recovered_engine(tmp_path, monkeypatch)
    ready = engine.incidents.get(item["id"])
    assert ready["restriction"] == "ready_for_release"
    assert ready["review_policy"] == "arming"
    engine.reconciliation_evidence["started_sequence"] = 0
    engine.refresh_incidents()
    assert engine.incidents.get(item["id"])["restriction"] == "held"
    assert not engine.store.get("incident", "watchdog")["resolved"]


def test_engine_fault_is_dedicated_review_with_optional_notes(tmp_path, monkeypatch):
    engine, item, _ = recovered_engine(tmp_path, monkeypatch, "engine_fault")
    ready = engine.incidents.get(item["id"])
    assert ready["review_policy"] == "dedicated"
    released = engine.review_incident(
        item["id"],
        revision=ready["revision"],
        actor="operator-fixture",
    )
    assert released["restriction"] == "released"
    assert released["investigation"] == "open"
    assert released["release_reason"] == "Operator acknowledged verified recovery."


def test_incident_detail_reports_checks_and_stability(tmp_path, monkeypatch):
    engine, item, _ = recovered_engine(tmp_path, monkeypatch, "order_uncertain")
    detail = engine.incident_detail(item["id"])
    assert detail["recovery"]["can_release"]
    assert detail["recovery"]["remaining_seconds"] == 0
    assert all(check["passed"] for check in detail["recovery"]["checks"])
    engine.reconciled = False
    detail = engine.incident_detail(item["id"])
    assert not detail["recovery"]["can_release"]
    assert any(not check["passed"] for check in detail["recovery"]["checks"])
    with pytest.raises(Conflict):
        engine.review_incident(item["id"])


def test_health_expiring_during_review_fails_closed_without_an_engine_fault(tmp_path, monkeypatch):
    engine, item, _ = recovered_engine(tmp_path, monkeypatch, "engine_fault")
    good = engine.watchdog_status()
    records = iter([good, {"ready": False, "detail": "Heartbeat expired during review."}])
    monkeypatch.setattr(engine, "watchdog_status", lambda: next(records))
    evidence, detail = engine._incident_evidence(engine.incidents.get(item["id"]))
    assert evidence is None and "expired" in detail


def test_restart_cannot_reuse_previous_recovery_window(tmp_path, monkeypatch):
    engine, item, _ = recovered_engine(tmp_path, monkeypatch)
    restarted = Engine(engine.store, BrokerDouble)
    restarted.refresh_incidents()
    assert restarted.incidents.get(item["id"])["restriction"] == "held"


def arm_fixture(engine, monkeypatch):
    from trading_oms_backend.workspace.graph import templates

    draft = engine.store.save_draft(
        None, "Incident authorization fixture", templates()[0]["document"], 0
    )
    version = engine.store.publish(draft["id"], 1)
    run = {
        "id": "selected-run",
        "strategy_id": draft["id"],
        "version": version["version"],
        "conid": 1,
        "symbol": "FIXTURE",
        "armed": False,
        "position": "0",
        "entries": 0,
    }
    engine.store.put("run", run["id"], run)
    engine.store.put("run", "other-run", {**run, "id": "other-run"})
    engine.data[1] = {"warm": True, "live": True, "subscription_status": "subscribed"}
    monkeypatch.setattr(engine, "_runtime", lambda *args, **kwargs: {})

    def preview(*args):
        engine.refresh_incidents()
        selected = [engine.store.get("run", run["id"])]
        holds = engine.incidents.applicable(selected)
        return {
            "eligible": not holds,
            "eligible_after_recovery_ack": bool(holds)
            and all(
                i["restriction"] == "ready_for_release" and i["review_policy"] == "arming"
                for i in holds
            ),
            "runs": selected,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "limits": {"risk": "10"},
            "authorization": "supervised_paper_session",
        }

    monkeypatch.setattr(engine, "arm_preview", preview)
    return run


def test_recovery_and_arm_are_atomic_idempotent_and_do_not_arm_other_runs(tmp_path, monkeypatch):
    engine, item, _ = recovered_engine(tmp_path, monkeypatch)
    run = arm_fixture(engine, monkeypatch)
    ready = engine.incidents.get(item["id"])
    request = dict(
        ids=[run["id"]],
        mutation_id="fixture-arm",
        recovery_acknowledgments=[{"id": ready["id"], "revision": ready["revision"]}],
        review_instance=engine.process_identity,
    )
    with pytest.raises(Conflict):
        engine.arm([run["id"]], "missing-ack")
    assert engine.arm(**request) == {"armed": [run["id"]]}
    released = engine.incidents.get(item["id"])
    assert released["restriction"] == "released"
    assert released["release_evidence"]["engine_instance"] == engine.process_identity
    assert engine.store.get("run", run["id"])["armed"]
    assert not engine.store.get("run", "other-run")["armed"]
    before = engine.incidents.watermark()
    engine.arm(**request)
    assert engine.incidents.watermark() == before


def test_emergency_during_confirmation_rolls_back_recovery_release(tmp_path, monkeypatch):
    engine, item, _ = recovered_engine(tmp_path, monkeypatch)
    run = arm_fixture(engine, monkeypatch)
    ready = engine.incidents.get(item["id"])
    engine.store.set_emergency(True)
    with pytest.raises(Conflict, match="Emergency"):
        engine.arm(
            [run["id"]],
            "emergency-race",
            recovery_acknowledgments=[{"id": ready["id"], "revision": ready["revision"]}],
            review_instance=engine.process_identity,
        )
    assert engine.incidents.get(item["id"])["restriction"] == "ready_for_release"
    assert not engine.store.get("run", run["id"])["armed"]
    assert not engine.store.get("mutation", "emergency-race")


@pytest.mark.parametrize("change", ["recurrence", "instance", "stale_health", "dedicated"])
def test_recovery_confirmation_rejects_stale_or_inapplicable_consent(tmp_path, monkeypatch, change):
    engine, item, _ = recovered_engine(
        tmp_path, monkeypatch, "engine_fault" if change == "dedicated" else "watchdog"
    )
    run = arm_fixture(engine, monkeypatch)
    ready = engine.incidents.get(item["id"])
    instance = engine.process_identity
    if change == "recurrence":
        engine.incident("watchdog", "Failure returned")
    if change == "instance":
        instance = "another-engine"
    if change == "stale_health":
        (tmp_path / "watchdog-health.json").unlink()
    with pytest.raises(Conflict):
        engine.arm(
            [run["id"]],
            "stale-review",
            recovery_acknowledgments=[{"id": ready["id"], "revision": ready["revision"]}],
            review_instance=instance,
        )
    assert not engine.store.get("run", run["id"])["armed"]
    assert engine.incidents.get(item["id"])["restriction"] != "released"


def test_new_hold_after_reservation_blocks_dispatch_without_sending_order(tmp_path):
    from test_workspace_unified import crypto_engine, crypto_entry

    engine, run = crypto_engine(tmp_path)
    reserve = engine.store.reserve_order

    def fault_after_reservation(*args, **kwargs):
        result = reserve(*args, **kwargs)
        engine.incident("engine_fault", "Late fault")
        return result

    engine.store.reserve_order = fault_after_reservation
    crypto_entry(engine, run)
    assert not engine.broker.submitted
    assert engine.store.orders()[0]["state"] == "cancelled"
    assert not engine.store.list("reservation")[0]["active"]


def test_quote_expiring_after_reservation_retires_intent_without_disarming_quiet_run(tmp_path):
    from test_workspace_unified import crypto_engine, crypto_entry

    engine, run = crypto_engine(tmp_path)
    reserve = engine.store.reserve_order

    def age_quote(*args, **kwargs):
        result = reserve(*args, **kwargs)
        engine.quotes[run["conid"]]["ask"]["received_at"] = "2000-01-01T00:00:00+00:00"
        return result

    engine.store.reserve_order = age_quote
    crypto_entry(engine, run)
    assert not engine.broker.submitted
    assert engine.store.orders()[0]["state"] == "cancelled"
    assert engine.store.get("run", run["id"])["armed"]
    assert not engine.incidents.open()
