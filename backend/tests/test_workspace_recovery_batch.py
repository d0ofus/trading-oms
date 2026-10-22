import pytest
from test_workspace_incidents import recovered_engine

from trading_oms_backend.workspace.store import Conflict


def test_combined_recovery_explicit_atomic_idempotent(tmp_path, monkeypatch):
    e, item, _ = recovered_engine(tmp_path, monkeypatch)
    e.incident("engine_fault", "Dedicated review")
    # Reconciliation after every currently observed failure, without releasing it.
    e.reconciliation_evidence["started_sequence"] = e.incidents.watermark()
    p = e.recovery_batch_preview()
    assert [i["id"] for i in p["items"]] == [item["id"]]
    result = e.recovery_batch_confirm(p["preview_id"], "mutation", "operator")
    assert e.recovery_batch_confirm(p["preview_id"], "mutation", "operator") == result
    assert e.incidents.get(item["id"])["restriction"] == "released"
    assert e.incidents.open()[0]["code"] == "engine_fault"
    assert not e.broker.submitted and not e.broker.cancelled


def test_changed_episode_or_health_rejects_batch(tmp_path, monkeypatch):
    e, item, _ = recovered_engine(tmp_path, monkeypatch)
    p = e.recovery_batch_preview()
    e.incident("watchdog", "Recurrence")
    with pytest.raises(Conflict):
        e.recovery_batch_confirm(p["preview_id"], "mutation", "operator")
    assert e.incidents.get(item["id"])["restriction"] == "held"


def test_contract_scoped_feed_is_routine_but_unscoped_unknown_is_dedicated(tmp_path, monkeypatch):
    e, _, _ = recovered_engine(tmp_path, monkeypatch)
    a = e.incidents.raise_incident("trade_feed_failure", "Feed", e.process_identity, conid=42)
    b = e.incidents.raise_incident("market_data_failure", "Unknown", e.process_identity)
    c = e.incidents.raise_incident("broker_201", "Rejection", e.process_identity)
    assert a["review_policy"] == "arming"
    assert b["review_policy"] == c["review_policy"] == "dedicated"


def test_service_recovery_requires_a_later_matching_service_observation(tmp_path, monkeypatch):
    from trading_oms_backend.workspace.service_status import service_diagnostic

    e, legacy, _ = recovered_engine(tmp_path, monkeypatch, "broker_2105")
    assert e.incidents.get(legacy["id"])["review_policy"] == "arming"
    failure = service_diagnostic(2105, "HMDS data farm connection is broken:ushmds")
    e.observe({"type": "broker_error", "request": -1, "code": 2105, "service": failure})
    item = next(i for i in e.incidents.open() if i.get("diagnostic"))
    e.reconciliation_evidence["started_sequence"] = e.incidents.watermark()
    assert not e._incident_evidence(item)[0]
    e.observe(
        {
            "type": "broker_error",
            "request": -1,
            "code": 2106,
            "service": service_diagnostic(2106, "HMDS data farm connection is OK:euhmds"),
        }
    )
    assert not e._incident_evidence(item)[0]
    e.observe(
        {
            "type": "broker_error",
            "request": -1,
            "code": 2106,
            "service": service_diagnostic(2106, "HMDS data farm connection is OK:ushmds"),
        }
    )
    assert e._incident_evidence(e.incidents.get(item["id"]))[0]
    # A good transport connection alone did not establish history farm recovery.
    assert e.incidents.get(item["id"])["restriction"] == "held"


def test_service_parser_never_retains_unknown_or_sensitive_text():
    from trading_oms_backend.workspace.service_status import service_diagnostic

    for message in (
        "raw-private-fixture",
        "HMDS data farm connection is OK:DU000000",
        "HMDS data farm connection is OK:unknownfarm",
        "Rejected:ushmds",
        "HMDS data farm connection is OK:ushmds secret",
    ):
        assert service_diagnostic(2106, message) is None
