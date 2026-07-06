from __future__ import annotations

import pytest

from trading_oms_backend.config import ConfigError, Settings


def test_settings_default_to_paper_mode_with_live_trading_disabled() -> None:
    settings = Settings.from_env({})

    assert settings.app_mode == "paper"
    assert settings.live_trading_enabled is False


def test_settings_allow_simulation_mode() -> None:
    settings = Settings.from_env({"APP_MODE": "simulation"})

    assert settings.app_mode == "simulation"
    assert settings.live_trading_enabled is False


def test_settings_reject_live_mode() -> None:
    with pytest.raises(ConfigError, match="APP_MODE"):
        Settings.from_env({"APP_MODE": "live"})


def test_settings_reject_enabled_live_trading_flag() -> None:
    with pytest.raises(ConfigError, match="live trading"):
        Settings.from_env({"LIVE_TRADING_ENABLED": "true"})
