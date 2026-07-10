from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from trading_oms_backend import read_models
from trading_oms_backend.config import Settings
from trading_oms_backend.read_models import (
    AlertReadModel,
    ApprovalTicketReadModel,
    AuditEventReadModel,
    OperationsReadModel,
    OperatorSessionReadModel,
    OrderReadModel,
    PaperTradingOperatorReadModel,
    PositionReadModel,
    ReadinessReadModel,
    ReadModelError,
    RiskDecisionReadModel,
    SafetyPostureReadModel,
    SignalReadModel,
    build_demo_operations_read_model,
)

FORBIDDEN_READ_AFFORDANCE_KEYS = {
    "account",
    "account_id",
    "api_key",
    "approve_action",
    "approve_url",
    "authorization",
    "broker_host",
    "broker_port",
    "cancel_action",
    "cancel_url",
    "certificate",
    "connect_action",
    "connect_url",
    "credential",
    "host",
    "password",
    "place_order_url",
    "port",
    "private_key",
    "reject_action",
    "reject_url",
    "route",
    "secret",
    "socket",
    "submit_action",
    "submit_url",
    "token",
    "transmit",
    "transmit_url",
}


def test_safety_posture_read_model_from_settings_is_read_only_and_safe() -> None:
    posture = SafetyPostureReadModel.from_settings(
        Settings(app_env="development", app_mode="paper", live_trading_enabled=False),
    )

    assert posture.to_json_dict() == {
        "schema_version": 1,
        "app_env": "development",
        "app_mode": "paper",
        "live_trading_enabled": False,
        "broker_connectivity": "not_configured",
        "alert_delivery": "local_noop",
        "approval_mode": "manual_required",
        "data_source": "local_read_model",
    }

    with pytest.raises(FrozenInstanceError):
        posture.live_trading_enabled = True  # type: ignore[misc]


def test_read_model_json_shapes_are_stable() -> None:
    audit_event = AuditEventReadModel(
        sequence=1,
        event_type="risk.decision.evaluated",
        timestamp="2026-07-08T00:00:00Z",
        summary="Risk decision blocked",
        run_id="sim-run-001",
        symbol="AAPL",
        order_id="order-001",
        ticket_id="ticket-001",
        severity="warning",
    )
    signal = SignalReadModel(
        signal_id="signal-001",
        strategy_id="strategy-001",
        symbol="AAPL",
        signal="long_bias",
        reason="close_above_sma",
        bar_start_timestamp="2026-07-08T00:00:00Z",
        bar_end_timestamp="2026-07-08T00:01:00Z",
    )
    risk = RiskDecisionReadModel(
        request_id="risk-001",
        evaluated_at="2026-07-08T00:01:00Z",
        symbol="AAPL",
        risk_intent="increase",
        result="blocked",
        failed_check_names=("market_data_freshness",),
    )
    ticket = ApprovalTicketReadModel(
        ticket_id="ticket-001",
        order_id="order-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        status="pending",
        risk_decision_id="risk-001",
        created_at="2026-07-08T00:02:00Z",
        expires_at="2026-07-08T00:12:00Z",
    )
    order = OrderReadModel(
        order_id="order-001",
        client_order_id="client-001",
        symbol="AAPL",
        side="buy",
        quantity=10,
        state="PENDING_APPROVAL",
        updated_at="2026-07-08T00:02:00Z",
        risk_decision_id="risk-001",
        approval_reference=None,
        requires_reconciliation=False,
        cumulative_filled_quantity=0,
        leaves_quantity=10,
    )
    position = PositionReadModel(
        position_id="position-001",
        symbol="AAPL",
        quantity=10,
        average_price=101.25,
        protection_status="expected_protection_present",
        updated_at="2026-07-08T00:03:00Z",
    )
    alert = AlertReadModel(
        alert_id="alert-001",
        severity="critical",
        channel="local",
        status="recorded",
        title="Protection review required",
        created_at="2026-07-08T00:04:00Z",
        source_event_reference="position-001",
    )
    readiness = ReadinessReadModel(
        evaluation_id="readiness-001",
        evaluated_at="2026-07-08T00:05:00Z",
        result="not_ready",
        failed_checks=("emergency_stop_implemented",),
        required_human_action="collect_missing_evidence",
    )
    operator_session = OperatorSessionReadModel(
        operator_id="human-operator-001",
        auth_state="local_development",
        auth_method="local_header",
        roles=("admin",),
        permissions=(
            "view_operations",
            "approve_simulation",
            "administer_system",
        ),
    )
    paper_trading = PaperTradingOperatorReadModel(
        adapter_name="ibkr_paper",
        paper_mode="paper",
        live_trading_enabled=False,
        connection_state="unknown_requires_reconciliation",
        requires_reconciliation=True,
        reconciliation_summary="stale_callback_requires_review",
        order_status="PARTIALLY_FILLED",
        order_client_reference="client-paper-001",
        status_callback_state="accepted_status_update",
        fill_callback_state="accepted_fill_update",
        cumulative_filled_quantity=4,
        leaves_quantity=6,
        updated_at="2026-07-08T00:06:00Z",
    )

    assert audit_event.to_json_dict() == {
        "schema_version": 1,
        "sequence": 1,
        "event_type": "risk.decision.evaluated",
        "timestamp": "2026-07-08T00:00:00Z",
        "summary": "Risk decision blocked",
        "run_id": "sim-run-001",
        "symbol": "AAPL",
        "order_id": "order-001",
        "ticket_id": "ticket-001",
        "severity": "warning",
    }
    assert signal.to_json_dict()["signal"] == "long_bias"
    assert risk.to_json_dict()["failed_check_names"] == ["market_data_freshness"]
    assert ticket.to_json_dict()["status"] == "pending"
    assert order.to_json_dict()["state"] == "PENDING_APPROVAL"
    assert position.to_json_dict()["source"] == "simulation"
    assert alert.to_json_dict()["status"] == "recorded"
    assert readiness.to_json_dict() == {
        "schema_version": 1,
        "evaluation_id": "readiness-001",
        "evaluated_at": "2026-07-08T00:05:00Z",
        "result": "not_ready",
        "failed_checks": ["emergency_stop_implemented"],
        "required_human_action": "collect_missing_evidence",
        "live_trading_enabled": False,
        "live_trading_authorized": False,
    }
    assert operator_session.to_json_dict() == {
        "schema_version": 1,
        "operator_id": "human-operator-001",
        "auth_state": "local_development",
        "auth_method": "local_header",
        "roles": ["admin"],
        "permissions": [
            "view_operations",
            "approve_simulation",
            "administer_system",
        ],
        "can_view_operations": True,
        "can_approve_simulation": True,
        "can_administer_system": True,
    }
    assert paper_trading.to_json_dict() == {
        "schema_version": 1,
        "adapter_name": "ibkr_paper",
        "paper_mode": "paper",
        "live_trading_enabled": False,
        "connection_state": "unknown_requires_reconciliation",
        "requires_reconciliation": True,
        "reconciliation_summary": "stale_callback_requires_review",
        "order_status": "PARTIALLY_FILLED",
        "order_client_reference": "client-paper-001",
        "status_callback_state": "accepted_status_update",
        "fill_callback_state": "accepted_fill_update",
        "cumulative_filled_quantity": 4,
        "leaves_quantity": 6,
        "updated_at": "2026-07-08T00:06:00Z",
    }


def test_paper_trading_operator_read_model_blocks_live_or_non_paper_modes() -> None:
    with pytest.raises(ReadModelError, match="paper_mode must remain paper"):
        PaperTradingOperatorReadModel(
            adapter_name="ibkr_paper",
            paper_mode="live",
            live_trading_enabled=False,
            connection_state="connected",
            requires_reconciliation=False,
            reconciliation_summary="clean",
            order_status="ACCEPTED",
            order_client_reference="client-paper-001",
            status_callback_state="accepted_status_update",
            fill_callback_state="no_fill_callback",
            cumulative_filled_quantity=0,
            leaves_quantity=1,
            updated_at="2026-07-08T00:06:00Z",
        )

    with pytest.raises(ReadModelError, match="live_trading_enabled must remain false"):
        PaperTradingOperatorReadModel(
            adapter_name="ibkr_paper",
            paper_mode="paper",
            live_trading_enabled=True,
            connection_state="connected",
            requires_reconciliation=False,
            reconciliation_summary="clean",
            order_status="ACCEPTED",
            order_client_reference="client-paper-001",
            status_callback_state="accepted_status_update",
            fill_callback_state="no_fill_callback",
            cumulative_filled_quantity=0,
            leaves_quantity=1,
            updated_at="2026-07-08T00:06:00Z",
        )


def test_operator_session_read_model_blocks_missing_permissions() -> None:
    with pytest.raises(ReadModelError, match="view_operations"):
        OperatorSessionReadModel(
            operator_id="viewer-operator-001",
            auth_state="local_development",
            auth_method="local_header",
            roles=("viewer",),
            permissions=(),
        )


def test_demo_operations_read_model_contains_every_expected_read_section() -> None:
    model = build_demo_operations_read_model(
        settings=Settings(app_env="development", app_mode="simulation"),
    )

    assert isinstance(model, OperationsReadModel)
    payload = model.to_json_dict()

    assert payload["schema_version"] == 1
    assert payload["safety"]["app_mode"] == "simulation"
    assert payload["safety"]["live_trading_enabled"] is False
    assert sorted(payload) == [
        "alerts",
        "approval_tickets",
        "audit_events",
        "operator_session",
        "orders",
        "paper_trading",
        "positions",
        "readiness",
        "risk_decisions",
        "safety",
        "schema_version",
        "signals",
    ]
    assert len(payload["audit_events"]) >= 1
    assert len(payload["signals"]) >= 1
    assert len(payload["risk_decisions"]) >= 1
    assert len(payload["approval_tickets"]) >= 1
    assert len(payload["orders"]) >= 1
    assert len(payload["positions"]) >= 1
    assert len(payload["alerts"]) >= 1
    assert payload["paper_trading"]["paper_mode"] == "paper"
    assert payload["operator_session"]["operator_id"] == "human-operator-001"
    assert payload["operator_session"]["can_view_operations"] is True
    assert payload["operator_session"]["can_approve_simulation"] is True
    assert payload["operator_session"]["can_administer_system"] is True
    assert payload["paper_trading"]["live_trading_enabled"] is False
    assert payload["paper_trading"]["requires_reconciliation"] is True
    assert payload["readiness"]["live_trading_authorized"] is False


def test_read_model_payloads_exclude_action_broker_network_and_secret_affordance_keys() -> None:
    model = build_demo_operations_read_model()

    assert FORBIDDEN_READ_AFFORDANCE_KEYS.isdisjoint(_all_payload_keys(model.to_json_dict()))


def test_read_models_module_does_not_define_mutation_or_transport_behavior() -> None:
    source = inspect.getsource(read_models).lower()

    forbidden_source_tokens = [
        "def submit",
        "def approve",
        "def reject",
        "def cancel",
        "def connect",
        "def transmit",
        "import socket",
        "from socket",
        "httpx",
        "requests",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "place_order",
        "submit_order",
        "transmit_order",
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
