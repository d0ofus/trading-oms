from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import app


def test_healthz_reports_safe_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_ACCOUNT_MODE", raising=False)
    monkeypatch.delenv("IBKR_HOST", raising=False)
    monkeypatch.delenv("IBKR_PORT", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example:placeholder@localhost:5432/app")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "placeholder-token-value")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "placeholder-chat-id")

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_env": "development",
        "app_mode": "paper",
        "live_trading_enabled": False,
        "ibkr_account_mode": "paper",
        "broker_connectivity": "not_configured",
    }
