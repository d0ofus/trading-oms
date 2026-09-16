from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from trading_oms_backend.workspace.acceptance import accept_session, observe_session, session_status
from trading_oms_backend.workspace.store import Conflict, Store


def test_actual_session_record_requires_flat_reconciled_completion_and_review(tmp_path):
    store = Store(tmp_path)
    store.put("run", "run", {"session_date": "2026-09-15", "unattended": True})
    engine = SimpleNamespace(
        store=store, process_identity="process", reconciled=True, owned=lambda: {}
    )
    observe_session(engine, datetime(2026, 9, 15, 14, tzinfo=UTC))
    with pytest.raises(Conflict):
        accept_session(store, "2026-09-15", True)
    observe_session(engine, datetime(2026, 9, 15, 20, 1, tzinfo=UTC))
    assert store.get("paper_session", "2026-09-15")["eligible"]
    accept_session(store, "2026-09-15", True)
    assert session_status(store)["consecutive_accepted"] == 1


def test_consecutive_acceptance_respects_exchange_sessions_and_missing_days(tmp_path):
    store = Store(tmp_path)
    for day in ["2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16"]:
        store.put("paper_session", day, {"date": day, "eligible": True})
        accept_session(store, day, True)
    assert session_status(store)["five_session_gate"]
    store.put("paper_session", "2026-09-18", {"date": "2026-09-18", "accepted": True})
    assert session_status(store)["consecutive_accepted"] == 1
