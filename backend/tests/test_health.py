from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from trading_oms_backend.app import app


def test_healthz_reports_safe_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_mode": "paper",
        "live_trading_enabled": False,
    }
