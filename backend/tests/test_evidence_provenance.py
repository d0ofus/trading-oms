from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import app, reset_emergency_stop_service
from trading_oms_backend.read_models import (
    OPERATIONS_READ_RESOURCES,
    LiveReadinessEvidenceDashboardReadModel,
    LiveReadinessEvidenceItemReadModel,
    ReadModelError,
    ReadModelProvenance,
    build_demo_operations_read_model,
)

READ_ENDPOINTS = {
    "/api/emergency-stop": "emergency_stop",
    "/api/operator-session": "operator_session",
    "/api/safety": "safety",
    "/api/audit-events": "audit_events",
    "/api/signals": "signals",
    "/api/risk-decisions": "risk_decisions",
    "/api/approval-tickets": "approval_tickets",
    "/api/orders": "orders",
    "/api/positions": "positions",
    "/api/alerts": "alerts",
    "/api/readiness": "readiness",
    "/api/paper-trading": "paper_trading",
    "/api/operational-controls": "operational_controls",
    "/api/live-readiness-evidence": "live_readiness_evidence",
}

CONTROLLED_CHECKLIST_CATEGORIES = {
    "external_review",
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
    "operator_signoff",
}


def test_demo_operations_provenance_covers_every_resource_fail_closed() -> None:
    model = build_demo_operations_read_model()

    assert set(OPERATIONS_READ_RESOURCES) == set(READ_ENDPOINTS.values())
    assert {item.resource for item in model.provenance} == set(OPERATIONS_READ_RESOURCES)

    for resource in OPERATIONS_READ_RESOURCES:
        provenance = model.provenance_for(resource)
        assert provenance.resource == resource
        assert provenance.broker_derived is False
        assert provenance.externally_verified is False
        assert "externally_unverified" in provenance.classifications

    for resource in {
        "audit_events",
        "signals",
        "risk_decisions",
        "approval_tickets",
        "orders",
        "positions",
        "alerts",
        "readiness",
    }:
        assert {
            "representative",
            "demo",
            "simulated",
            "local_only",
            "externally_unverified",
        }.issubset(model.provenance_for(resource).classifications)

    paper = model.provenance_for("paper_trading")
    assert {
        "representative",
        "demo",
        "local_only",
        "test_double",
        "adapter_only",
        "externally_unverified",
    }.issubset(paper.classifications)
    assert "not an authenticated IBKR paper session" in paper.summary

    emergency_stop = model.provenance_for("emergency_stop")
    assert emergency_stop.classifications == ("local_only", "externally_unverified")


def test_provenance_rejects_unsafe_or_ambiguous_claims() -> None:
    safe = ReadModelProvenance(
        resource="paper_trading",
        source="local_demo_read_model",
        classifications=("adapter_only", "externally_unverified"),
        broker_derived=False,
        externally_verified=False,
        summary="Representative adapter state only",
    )
    assert safe.to_json_dict()["broker_derived"] is False

    with pytest.raises(ReadModelError, match="broker_derived must remain false"):
        replace(safe, broker_derived=True)
    with pytest.raises(ReadModelError, match="externally_verified must remain false"):
        replace(safe, externally_verified=True)
    with pytest.raises(ReadModelError, match="known provenance classification"):
        replace(safe, classifications=("unknown", "externally_unverified"))
    with pytest.raises(ReadModelError, match="classifications must not contain duplicates"):
        replace(
            safe,
            classifications=("adapter_only", "adapter_only", "externally_unverified"),
        )
    with pytest.raises(ReadModelError, match="must include externally_unverified"):
        replace(safe, classifications=("adapter_only",))


def test_every_operations_endpoint_returns_matching_provenance_envelope(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    reset_emergency_stop_service()
    client = TestClient(app)

    for path, resource in READ_ENDPOINTS.items():
        response = client.get(path)
        payload = response.json()

        assert response.status_code == 200
        assert payload["schema_version"] == 1
        assert payload["resource"] == resource
        assert payload["provenance"]["resource"] == resource
        assert payload["provenance"]["broker_derived"] is False
        assert payload["provenance"]["externally_verified"] is False
        assert "externally_unverified" in payload["provenance"]["classifications"]
        assert "data" in payload


def test_demo_readiness_matches_every_controlled_checklist_row() -> None:
    dashboard = build_demo_operations_read_model().live_readiness_evidence
    payload = dashboard.to_json_dict()

    assert payload["result"] == "not_ready"
    assert {item["category"] for item in payload["evidence_items"]} == (
        CONTROLLED_CHECKLIST_CATEGORIES
    )
    assert payload["verified_evidence_count"] == 0
    assert payload["missing_evidence_count"] == 6
    assert payload["unverified_evidence_count"] == 8
    assert payload["expired_evidence_count"] == 0
    assert payload["contradictory_evidence_count"] == 0
    assert payload["blocking_evidence_count"] == 14
    assert all(item["status"] != "verified" for item in payload["evidence_items"])

    statuses = {item["category"]: item["status"] for item in payload["evidence_items"]}
    for category in {
        "live_readiness",
        "secret_management",
        "authentication_authorization",
        "emergency_stop",
        "observability",
        "audit_retention",
        "backup_restore",
        "reconciliation",
    }:
        assert statuses[category] == "unverified"


@pytest.mark.parametrize("blocking_status", ["missing", "unverified", "expired", "contradictory"])
def test_every_nonverified_evidence_state_blocks_final_review(
    blocking_status: str,
) -> None:
    item = _evidence_item(status=blocking_status)
    counts = {
        "missing": 0,
        "unverified": 0,
        "expired": 0,
        "contradictory": 0,
    }
    counts[blocking_status] = 1

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
            missing_evidence_count=counts["missing"],
            unverified_evidence_count=counts["unverified"],
            expired_evidence_count=counts["expired"],
            contradictory_evidence_count=counts["contradictory"],
            blocking_evidence_count=1,
            blocking_reason="mandatory_evidence_not_verified",
            evidence_items=(item,),
        )


def test_all_verified_evidence_can_only_reach_final_review_with_live_disabled() -> None:
    dashboard = LiveReadinessEvidenceDashboardReadModel(
        dashboard_id="live-readiness-evidence-001",
        evaluated_at="2026-07-08T00:08:00Z",
        result="ready_for_final_review",
        live_trading_enabled=False,
        live_trading_authorized=False,
        external_review_required=False,
        explicit_human_approval_required=False,
        verified_evidence_count=1,
        missing_evidence_count=0,
        unverified_evidence_count=0,
        expired_evidence_count=0,
        contradictory_evidence_count=0,
        blocking_evidence_count=0,
        blocking_reason="final_human_review_required",
        evidence_items=(_evidence_item(status="verified"),),
    )

    assert dashboard.result == "ready_for_final_review"
    assert dashboard.live_trading_enabled is False
    assert dashboard.live_trading_authorized is False


def _evidence_item(status: str) -> LiveReadinessEvidenceItemReadModel:
    return LiveReadinessEvidenceItemReadModel(
        evidence_id="evidence-external-review",
        category="external_review",
        label="External review evidence",
        status=status,
        required_for_final_review=True,
        summary="Independent review evidence posture",
        source_reference="docs/controlled-paper-production-rollout-checklist",
    )


def _set_safe_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_ACCOUNT_MODE", raising=False)
    monkeypatch.delenv("IBKR_HOST", raising=False)
    monkeypatch.delenv("IBKR_PORT", raising=False)
