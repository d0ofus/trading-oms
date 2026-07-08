from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from trading_oms_backend.config import get_settings
from trading_oms_backend.read_models import OperationsReadModel, build_demo_operations_read_model

app = FastAPI(title="Trading OMS", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "app_mode": settings.app_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "ibkr_account_mode": settings.ibkr_account_mode,
        "broker_connectivity": "not_configured",
    }


@app.get("/api/safety")
def get_safety() -> dict[str, Any]:
    return _operations_read_model().safety.to_json_dict()


@app.get("/api/audit-events")
def get_audit_events() -> list[dict[str, Any]]:
    return [event.to_json_dict() for event in _operations_read_model().audit_events]


@app.get("/api/signals")
def get_signals() -> list[dict[str, Any]]:
    return [signal.to_json_dict() for signal in _operations_read_model().signals]


@app.get("/api/risk-decisions")
def get_risk_decisions() -> list[dict[str, Any]]:
    return [decision.to_json_dict() for decision in _operations_read_model().risk_decisions]


@app.get("/api/approval-tickets")
def get_approval_tickets() -> list[dict[str, Any]]:
    return [ticket.to_json_dict() for ticket in _operations_read_model().approval_tickets]


@app.get("/api/orders")
def get_orders() -> list[dict[str, Any]]:
    return [order.to_json_dict() for order in _operations_read_model().orders]


@app.get("/api/positions")
def get_positions() -> list[dict[str, Any]]:
    return [position.to_json_dict() for position in _operations_read_model().positions]


@app.get("/api/alerts")
def get_alerts() -> list[dict[str, Any]]:
    return [alert.to_json_dict() for alert in _operations_read_model().alerts]


@app.get("/api/readiness")
def get_readiness() -> dict[str, Any]:
    return _operations_read_model().readiness.to_json_dict()


def _operations_read_model() -> OperationsReadModel:
    return build_demo_operations_read_model(get_settings())
