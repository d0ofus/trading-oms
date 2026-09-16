import pytest

from trading_oms_backend.workspace.qualification import (
    accept_review,
    profiles,
    qualification_checks,
    save_profile,
)
from trading_oms_backend.workspace.store import Conflict, Store


def test_profiles_are_versioned_and_cannot_relax_hard_limits(tmp_path):
    store = Store(tmp_path)
    first = {**profiles(store)[0], "id": "custom", "name": "Tighter limits", "shares": 2}
    first.pop("version")
    saved = save_profile(store, first)
    newer = save_profile(store, {**first, "shares": 1})
    assert saved["version"] == 1 and newer["version"] == 2
    assert store.get("risk_profile", "custom:1")["shares"] == 2
    for field, value in [
        ("shares", 11),
        ("runs", 6),
        ("notional", "1001"),
        ("daily_loss", "101"),
        ("planned_stop_risk", "11"),
    ]:
        with pytest.raises(ValueError):
            save_profile(store, {**first, field: value})


def test_unattended_requires_actual_evidence_and_recent_notification_tests(tmp_path):
    store = Store(tmp_path)
    profile = next(p for p in profiles(store) if p["id"] == "qualified")
    checks = qualification_checks(store, profile, True, True)
    assert not all(c["passed"] for c in checks)
    with pytest.raises(Conflict):
        accept_review(store, "supervised", True)
    store.put("qualification", "broker_evidence", {"smoke_completed": True})
    accept_review(store, "supervised", True)
    assert all(c["passed"] for c in qualification_checks(store, profile, False, True))
    with pytest.raises(Conflict):
        accept_review(store, "unattended", True)
    assert not all(c["passed"] for c in qualification_checks(store, profile, False, False))
