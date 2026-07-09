from __future__ import annotations

import inspect
import re
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend import app as app_module
from trading_oms_backend.app import app
from trading_oms_backend.read_models import build_demo_operations_read_model

FORBIDDEN_API_AFFORDANCE_KEYS = {
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

READ_ENDPOINTS = {
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
}


def test_read_only_api_endpoints_return_expected_read_model_sections(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    client = TestClient(app)
    expected = build_demo_operations_read_model().to_json_dict()

    for path, section_name in READ_ENDPOINTS.items():
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == expected[section_name]


def test_read_only_api_endpoints_do_not_implement_mutation_methods(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    client = TestClient(app)

    for path in READ_ENDPOINTS:
        assert client.post(path).status_code == 405
        assert client.put(path).status_code == 405
        assert client.patch(path).status_code == 405
        assert client.delete(path).status_code == 405


def test_read_only_api_responses_exclude_action_broker_network_and_secret_affordances(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_safe_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example:placeholder@localhost:5432/app")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "placeholder-token-value")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "placeholder-chat-id")
    client = TestClient(app)

    payloads = [client.get(path).json() for path in READ_ENDPOINTS]
    rendered_payloads = "\n".join(
        response.text for response in (client.get(path) for path in READ_ENDPOINTS)
    )

    for payload in payloads:
        assert FORBIDDEN_API_AFFORDANCE_KEYS.isdisjoint(_all_payload_keys(payload))

    assert "placeholder-token-value" not in rendered_payloads
    assert "placeholder-chat-id" not in rendered_payloads


def test_app_module_does_not_define_mutation_or_transport_routes() -> None:
    source = inspect.getsource(app_module).lower()

    post_routes = set(re.findall(r'@app\.post\("([^"]+)"', source))
    put_routes = set(re.findall(r'@app\.put\("([^"]+)"', source))
    assert post_routes == {
        "/api/approval-tickets/{ticket_id}/approve",
        "/api/approval-tickets/{ticket_id}/reject",
        "/api/workflows",
        "/api/workflows/{workflow_id}/simulation-runs",
    }
    assert put_routes == {"/api/workflows/{workflow_id}"}

    forbidden_source_tokens = [
        "@app.patch",
        "@app.delete",
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
