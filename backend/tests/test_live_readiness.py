from __future__ import annotations

import inspect
from typing import Any

import pytest

from trading_oms_backend import live_readiness
from trading_oms_backend.config import ConfigError, Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.live_readiness import (
    LIVE_TRADING_READINESS_EVENT_TYPE,
    LiveTradingReadinessDecision,
    LiveTradingReadinessError,
    LiveTradingReadinessEvidence,
    evaluate_live_trading_readiness,
)

EVALUATED_AT = "2026-07-06T00:04:00Z"


def complete_evidence(**overrides: Any) -> LiveTradingReadinessEvidence:
    values = {
        "paper_trading_history_reviewed": True,
        "risk_engine_complete": True,
        "oms_state_machine_complete": True,
        "event_journal_complete": True,
        "approval_flow_complete": True,
        "reconnect_reconciliation_tested": True,
        "chaos_tests_passing": True,
        "duplicate_order_prevention_tested": True,
        "stale_data_blocking_tested": True,
        "emergency_stop_implemented": True,
        "secrets_management_reviewed": True,
        "network_exposure_reviewed": True,
        "external_code_review_completed": True,
        "explicit_human_approval_recorded": True,
    }
    values.update(overrides)
    return LiveTradingReadinessEvidence(**values)


def test_live_readiness_default_evidence_is_not_ready_and_journaled(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    decision = evaluate_live_trading_readiness(
        evidence=LiveTradingReadinessEvidence(),
        journal=journal,
        evaluation_id="readiness-001",
        evaluated_at=EVALUATED_AT,
    )

    assert decision.result == "not_ready"
    assert decision.live_trading_enabled is False
    assert decision.live_trading_authorized is False
    assert decision.required_human_action == "collect_missing_evidence"
    assert len(decision.failed_checks()) == len(decision.checks)
    assert decision.check_by_name("paper_trading_history_reviewed").reason == "missing_evidence"

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == LIVE_TRADING_READINESS_EVENT_TYPE
    assert records[0].timestamp == EVALUATED_AT
    assert records[0].payload == decision.to_json_dict()


def test_live_readiness_missing_single_evidence_item_blocks_final_review(tmp_path) -> None:
    decision = evaluate_live_trading_readiness(
        evidence=complete_evidence(emergency_stop_implemented=False),
        journal=JsonlEventJournal(tmp_path / "events.jsonl"),
        evaluation_id="readiness-002",
        evaluated_at=EVALUATED_AT,
    )

    assert decision.result == "not_ready"
    assert decision.failed_check_names() == ["emergency_stop_implemented"]
    assert decision.check_by_name("emergency_stop_implemented").reason == "missing_evidence"
    assert decision.live_trading_enabled is False
    assert decision.live_trading_authorized is False


def test_live_readiness_complete_evidence_is_review_only_not_enablement(tmp_path) -> None:
    decision = evaluate_live_trading_readiness(
        evidence=complete_evidence(),
        journal=JsonlEventJournal(tmp_path / "events.jsonl"),
        evaluation_id="readiness-003",
        evaluated_at=EVALUATED_AT,
    )

    assert decision == LiveTradingReadinessDecision(
        evaluation_id="readiness-003",
        evaluated_at=EVALUATED_AT,
        result="ready_for_final_review",
        checks=decision.checks,
        required_human_action="external_review_and_explicit_rollout_approval",
        live_trading_enabled=False,
        live_trading_authorized=False,
    )
    assert decision.failed_checks() == []
    assert all(check.status == "passed" for check in decision.checks)
    assert decision.to_json_dict()["live_trading_enabled"] is False
    assert decision.to_json_dict()["live_trading_authorized"] is False


def test_live_readiness_rejects_requested_live_enablement(tmp_path) -> None:
    journal = JsonlEventJournal(tmp_path / "events.jsonl")

    with pytest.raises(LiveTradingReadinessError, match="cannot enable live trading"):
        evaluate_live_trading_readiness(
            evidence=complete_evidence(),
            journal=journal,
            evaluation_id="readiness-004",
            evaluated_at=EVALUATED_AT,
            requested_live_trading_enabled=True,
        )

    assert journal.read_all() == []


def test_settings_still_reject_live_trading_enabled() -> None:
    with pytest.raises(ConfigError, match="live trading"):
        Settings.from_env({"LIVE_TRADING_ENABLED": "true"})


def test_live_readiness_payloads_and_module_exclude_credentials_network_and_submission(
    tmp_path,
) -> None:
    decision = evaluate_live_trading_readiness(
        evidence=complete_evidence(),
        journal=JsonlEventJournal(tmp_path / "events.jsonl"),
        evaluation_id="readiness-safe-001",
        evaluated_at=EVALUATED_AT,
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "authorization",
        "broker_order_id",
        "certificate",
        "credential",
        "host",
        "password",
        "port",
        "private_key",
        "route",
        "secret",
        "socket",
        "submit",
        "token",
        "transmit",
    }
    assert forbidden_keys.isdisjoint(_all_payload_keys(decision.to_json_dict()))

    source = inspect.getsource(live_readiness).lower()
    forbidden_source_tokens = [
        "import socket",
        "from socket",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "submit_order",
        "transmit_order",
        "place_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


def _all_payload_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested_value in value.values():
            keys.update(_all_payload_keys(nested_value))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_all_payload_keys(item))
        return keys
    return set()
