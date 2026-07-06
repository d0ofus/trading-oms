from __future__ import annotations

from fastapi import FastAPI

from trading_oms_backend.config import get_settings

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
