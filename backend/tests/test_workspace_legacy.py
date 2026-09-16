import pytest

from trading_oms_backend.workspace.graph import GraphError
from trading_oms_backend.workspace.legacy import import_history, migrate_definition
from trading_oms_backend.workspace.store import Store


def test_legacy_approvals_are_read_only_evidence_and_sensitive_fields_are_redacted(tmp_path):
    store = Store(tmp_path)
    rows = [
        {
            "schema_version": 1,
            "sequence": 1,
            "type": "approval.approved",
            "timestamp": "2026-09-15T14:00:00Z",
            "payload": {"account_id": "fixture-only", "approved": True},
        }
    ]
    result = import_history(store, "Historical approvals", rows)
    assert result["paper_authorization"] is False
    assert store.list("legacy_record")[0]["payload"]["account_id"] == "[redacted]"
    assert not store.list("run")
    assert import_history(store, "Repeated", rows)["id"] == result["id"]
    assert len(store.list("legacy_record")) == 1


def test_legacy_strategy_requires_new_protection_review_before_publication(tmp_path):
    store = Store(tmp_path)
    draft = migrate_definition(
        store,
        "Historical SMA",
        {
            "schema_version": 1,
            "strategy_id": "fixture-sma",
            "strategy_type": "close_above_sma",
            "mode": "replay",
            "symbol": "AAPL",
            "bar_timeframe_seconds": 60,
            "parameters": {"lookback_bars": 5, "price_source": "close"},
        },
    )
    assert draft["document"]["settings"]["evaluation"] == "bar_close"
    with pytest.raises(GraphError):
        store.publish(draft["id"], draft["revision"])
    assert not store.list("run")
