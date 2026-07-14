from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import app, reset_emergency_stop_service
from trading_oms_backend.read_models import (
    AuditRetentionReadModel,
    BackupRestoreReadModel,
    IncidentResponseReadModel,
    ObservabilityEventReadModel,
    ObservabilityMetricReadModel,
    OperationalControlsReadModel,
    ReadModelError,
    build_demo_operations_read_model,
)

FORBIDDEN_OPERATIONAL_KEYS = {
    "account",
    "account_id",
    "api_key",
    "authorization",
    "broker_host",
    "broker_port",
    "cancel_action",
    "certificate",
    "connect_action",
    "credential",
    "host",
    "password",
    "place_order_url",
    "port",
    "private_key",
    "route",
    "secret",
    "socket",
    "submit_action",
    "token",
    "transmit",
}


def test_operational_controls_read_model_exposes_safe_local_operating_posture() -> None:
    controls = build_demo_operations_read_model().operational_controls
    payload = controls.to_json_dict()

    assert payload["schema_version"] == 1
    assert payload["live_trading_enabled"] is False
    assert payload["production_rollout_authorized"] is False
    assert [metric["metric_name"] for metric in payload["metrics"]] == [
        "system.health",
        "safety.posture",
        "emergency_stop.state",
        "audit_journal.health",
        "backup.status",
        "incident.response",
    ]
    assert payload["retention"]["destructive_retention_enabled"] is False
    assert payload["retention"]["append_only_journal_required"] is True
    assert payload["backup_restore"]["external_storage_configured"] is False
    assert payload["backup_restore"]["restore_verification_status"] == "local_plan_documented"
    assert payload["incident_response"]["active_incident_state"] == "none_declared"
    assert payload["incident_response"]["emergency_stop_required_for_critical_incidents"] is True
    assert FORBIDDEN_OPERATIONAL_KEYS.isdisjoint(_all_payload_keys(payload))


def test_operational_controls_validation_blocks_unsafe_postures() -> None:
    with pytest.raises(ReadModelError, match="live_trading_enabled must remain false"):
        OperationalControlsReadModel(
            observed_at="2026-07-08T00:07:00Z",
            live_trading_enabled=True,
            production_rollout_authorized=False,
            metrics=(_metric(),),
            events=(_event(),),
            retention=_retention(),
            backup_restore=_backup_restore(),
            incident_response=_incident_response(),
        )

    with pytest.raises(ReadModelError, match="production_rollout_authorized must remain false"):
        OperationalControlsReadModel(
            observed_at="2026-07-08T00:07:00Z",
            live_trading_enabled=False,
            production_rollout_authorized=True,
            metrics=(_metric(),),
            events=(_event(),),
            retention=_retention(),
            backup_restore=_backup_restore(),
            incident_response=_incident_response(),
        )

    with pytest.raises(ReadModelError, match="destructive_retention_enabled must remain false"):
        AuditRetentionReadModel(
            policy_id="audit-retention-local-001",
            mode="retain_until_reviewed",
            minimum_retention_days=365,
            destructive_retention_enabled=True,
            append_only_journal_required=True,
            next_review_due_at="2026-08-08T00:00:00Z",
            status="planned_local_only",
        )

    with pytest.raises(ReadModelError, match="external_storage_configured must remain false"):
        BackupRestoreReadModel(
            plan_id="backup-restore-local-001",
            backup_status="local_plan_documented",
            restore_verification_status="local_plan_documented",
            last_verified_at="2026-07-08T00:07:00Z",
            storage_mode="local_encrypted_storage_required",
            external_storage_configured=True,
            redaction_status="redaction_required",
        )

    with pytest.raises(ReadModelError, match="emergency stop must be required"):
        IncidentResponseReadModel(
            plan_id="incident-response-local-001",
            active_incident_state="none_declared",
            severity_floor_for_operator_review="warning",
            emergency_stop_required_for_critical_incidents=False,
            post_incident_review_required=True,
            current_runbook_status="documented_local_playbook",
            last_reviewed_at="2026-07-08T00:07:00Z",
        )


def test_operational_controls_reject_unsafe_observability_text() -> None:
    with pytest.raises(ReadModelError, match="unsafe observability text"):
        ObservabilityMetricReadModel(
            metric_name="broker_host",
            metric_value=1,
            unit="count",
            status="ok",
            observed_at="2026-07-08T00:07:00Z",
            summary="Unsafe broker host shaped metric",
        )

    with pytest.raises(ReadModelError, match="unsafe observability text"):
        ObservabilityEventReadModel(
            event_id="observability-event-001",
            event_type="incident.response",
            observed_at="2026-07-08T00:07:00Z",
            severity="warning",
            summary="token: should not appear",
            journal_reference="journal_sequence:0",
        )


def test_operational_controls_api_is_read_only_and_safe(monkeypatch: MonkeyPatch) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "placeholder-token-value")
    client = TestClient(app)

    response = client.get("/api/operational-controls")
    payload = response.json()

    assert response.status_code == 200
    assert payload == build_demo_operations_read_model().to_api_envelope("operational_controls")
    assert client.post("/api/operational-controls").status_code == 405
    assert client.put("/api/operational-controls").status_code == 405
    assert client.patch("/api/operational-controls").status_code == 405
    assert client.delete("/api/operational-controls").status_code == 405
    assert FORBIDDEN_OPERATIONAL_KEYS.isdisjoint(_all_payload_keys(payload))
    assert "placeholder-token-value" not in response.text
    assert 'live_trading_enabled":true' not in response.text.replace(" ", "").lower()


def _metric() -> ObservabilityMetricReadModel:
    return ObservabilityMetricReadModel(
        metric_name="system.health",
        metric_value=1,
        unit="status",
        status="ok",
        observed_at="2026-07-08T00:07:00Z",
        summary="Local service health is visible",
    )


def _event() -> ObservabilityEventReadModel:
    return ObservabilityEventReadModel(
        event_id="observability-event-001",
        event_type="system.health",
        observed_at="2026-07-08T00:07:00Z",
        severity="informational",
        summary="Local observability snapshot recorded",
        journal_reference="journal_sequence:0",
    )


def _retention() -> AuditRetentionReadModel:
    return AuditRetentionReadModel(
        policy_id="audit-retention-local-001",
        mode="retain_until_reviewed",
        minimum_retention_days=365,
        destructive_retention_enabled=False,
        append_only_journal_required=True,
        next_review_due_at="2026-08-08T00:00:00Z",
        status="planned_local_only",
    )


def _backup_restore() -> BackupRestoreReadModel:
    return BackupRestoreReadModel(
        plan_id="backup-restore-local-001",
        backup_status="local_plan_documented",
        restore_verification_status="local_plan_documented",
        last_verified_at="2026-07-08T00:07:00Z",
        storage_mode="local_encrypted_storage_required",
        external_storage_configured=False,
        redaction_status="redaction_required",
    )


def _incident_response() -> IncidentResponseReadModel:
    return IncidentResponseReadModel(
        plan_id="incident-response-local-001",
        active_incident_state="none_declared",
        severity_floor_for_operator_review="warning",
        emergency_stop_required_for_critical_incidents=True,
        post_incident_review_required=True,
        current_runbook_status="documented_local_playbook",
        last_reviewed_at="2026-07-08T00:07:00Z",
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
