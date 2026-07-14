from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import app, reset_emergency_stop_service
from trading_oms_backend.read_models import (
    LiveReadinessEvidenceDashboardReadModel,
    LiveReadinessEvidenceItemReadModel,
    ReadModelError,
    build_demo_operations_read_model,
)

FORBIDDEN_EVIDENCE_KEYS = {
    "account",
    "account_id",
    "api_key",
    "approve_action",
    "approve_url",
    "authorization",
    "broker_host",
    "broker_port",
    "certificate",
    "connect_action",
    "connect_url",
    "credential",
    "host",
    "password",
    "port",
    "private_key",
    "route",
    "secret",
    "socket",
    "submit_action",
    "token",
    "transmit",
}


def test_live_readiness_evidence_dashboard_exposes_all_unresolved_evidence() -> None:
    dashboard = build_demo_operations_read_model().live_readiness_evidence
    payload = dashboard.to_json_dict()

    assert payload["schema_version"] == 1
    assert payload["result"] == "not_ready"
    assert payload["live_trading_enabled"] is False
    assert payload["live_trading_authorized"] is False
    assert payload["external_review_required"] is True
    assert payload["explicit_human_approval_required"] is True
    assert payload["verified_evidence_count"] == 0
    assert payload["missing_evidence_count"] == 6
    assert payload["unverified_evidence_count"] == 8
    assert payload["expired_evidence_count"] == 0
    assert payload["contradictory_evidence_count"] == 0
    assert payload["blocking_evidence_count"] == 14
    assert payload["blocking_reason"] == "missing_and_unverified_controlled_rollout_evidence"
    assert {item["category"] for item in payload["evidence_items"]} == {
        "paper_trading_history",
        "live_readiness",
        "secret_management",
        "network_exposure",
        "authentication_authorization",
        "emergency_stop",
        "observability",
        "audit_retention",
        "backup_restore",
        "reconciliation",
        "rollback",
        "incident_response",
        "external_review",
        "operator_signoff",
    }
    assert [item["status"] for item in payload["evidence_items"]].count("missing") == 6
    assert [item["status"] for item in payload["evidence_items"]].count("unverified") == 8
    assert FORBIDDEN_EVIDENCE_KEYS.isdisjoint(_all_payload_keys(payload))


def test_live_readiness_evidence_validation_blocks_unsafe_postures() -> None:
    with pytest.raises(ReadModelError, match="live_trading_enabled must remain false"):
        LiveReadinessEvidenceDashboardReadModel(
            dashboard_id="live-readiness-evidence-001",
            evaluated_at="2026-07-08T00:08:00Z",
            result="not_ready",
            live_trading_enabled=True,
            live_trading_authorized=False,
            external_review_required=True,
            explicit_human_approval_required=True,
            verified_evidence_count=0,
            missing_evidence_count=1,
            unverified_evidence_count=0,
            expired_evidence_count=0,
            contradictory_evidence_count=0,
            blocking_evidence_count=1,
            blocking_reason="missing_external_review",
            evidence_items=(_evidence_item(status="missing"),),
        )

    with pytest.raises(ReadModelError, match="live_trading_authorized must remain false"):
        LiveReadinessEvidenceDashboardReadModel(
            dashboard_id="live-readiness-evidence-001",
            evaluated_at="2026-07-08T00:08:00Z",
            result="not_ready",
            live_trading_enabled=False,
            live_trading_authorized=True,
            external_review_required=True,
            explicit_human_approval_required=True,
            verified_evidence_count=0,
            missing_evidence_count=1,
            unverified_evidence_count=0,
            expired_evidence_count=0,
            contradictory_evidence_count=0,
            blocking_evidence_count=1,
            blocking_reason="missing_external_review",
            evidence_items=(_evidence_item(status="missing"),),
        )

    with pytest.raises(ReadModelError, match="result must be not_ready or ready_for_final_review"):
        LiveReadinessEvidenceDashboardReadModel(
            dashboard_id="live-readiness-evidence-001",
            evaluated_at="2026-07-08T00:08:00Z",
            result="ready_for_live",
            live_trading_enabled=False,
            live_trading_authorized=False,
            external_review_required=True,
            explicit_human_approval_required=True,
            verified_evidence_count=0,
            missing_evidence_count=1,
            unverified_evidence_count=0,
            expired_evidence_count=0,
            contradictory_evidence_count=0,
            blocking_evidence_count=1,
            blocking_reason="missing_external_review",
            evidence_items=(_evidence_item(status="missing"),),
        )

    with pytest.raises(ReadModelError, match="ready_for_final_review evidence must be verified"):
        LiveReadinessEvidenceDashboardReadModel(
            dashboard_id="live-readiness-evidence-001",
            evaluated_at="2026-07-08T00:08:00Z",
            result="ready_for_final_review",
            live_trading_enabled=False,
            live_trading_authorized=False,
            external_review_required=False,
            explicit_human_approval_required=False,
            verified_evidence_count=0,
            missing_evidence_count=1,
            unverified_evidence_count=0,
            expired_evidence_count=0,
            contradictory_evidence_count=0,
            blocking_evidence_count=1,
            blocking_reason="missing_external_review",
            evidence_items=(_evidence_item(status="missing"),),
        )


def test_live_readiness_evidence_rejects_unsafe_text() -> None:
    with pytest.raises(ReadModelError, match="unsafe observability text"):
        LiveReadinessEvidenceItemReadModel(
            evidence_id="evidence-001",
            category="paper_trading_history",
            label="Unsafe item",
            status="missing",
            required_for_final_review=True,
            summary="token: should not appear",
            source_reference="local_review",
        )


def test_live_readiness_evidence_api_is_read_only_and_safe(monkeypatch: MonkeyPatch) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "placeholder-token-value")
    client = TestClient(app)

    response = client.get("/api/live-readiness-evidence")
    payload = response.json()

    assert response.status_code == 200
    assert payload == build_demo_operations_read_model().to_api_envelope("live_readiness_evidence")
    assert client.post("/api/live-readiness-evidence").status_code == 405
    assert client.put("/api/live-readiness-evidence").status_code == 405
    assert client.patch("/api/live-readiness-evidence").status_code == 405
    assert client.delete("/api/live-readiness-evidence").status_code == 405
    assert FORBIDDEN_EVIDENCE_KEYS.isdisjoint(_all_payload_keys(payload))
    assert "placeholder-token-value" not in response.text
    assert 'live_trading_enabled":true' not in response.text.replace(" ", "").lower()


def _evidence_item(status: str) -> LiveReadinessEvidenceItemReadModel:
    return LiveReadinessEvidenceItemReadModel(
        evidence_id="evidence-001",
        category="external_review",
        label="External review",
        status=status,
        required_for_final_review=True,
        summary="Independent review evidence is missing",
        source_reference="docs/live-trading-readiness-checklist",
    )


def _set_safe_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_ACCOUNT_MODE", raising=False)
    monkeypatch.delenv("IBKR_HOST", raising=False)
    monkeypatch.delenv("IBKR_PORT", raising=False)


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
