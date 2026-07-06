from __future__ import annotations

import pytest

from trading_oms_backend.config import ConfigError, Settings


def test_settings_default_to_paper_mode_with_live_trading_disabled() -> None:
    settings = Settings.from_env({})

    assert settings.app_env == "development"
    assert settings.app_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.ibkr_account_mode == "paper"
    assert settings.ibkr_host == "127.0.0.1"
    assert settings.ibkr_port == 7497


def test_settings_allow_simulation_mode() -> None:
    settings = Settings.from_env({"APP_ENV": "test", "APP_MODE": "simulation"})

    assert settings.app_env == "test"
    assert settings.app_mode == "simulation"
    assert settings.live_trading_enabled is False


def test_settings_reject_unknown_app_env() -> None:
    with pytest.raises(ConfigError, match="APP_ENV"):
        Settings.from_env({"APP_ENV": "staging"})


def test_settings_reject_live_mode() -> None:
    with pytest.raises(ConfigError, match="APP_MODE"):
        Settings.from_env({"APP_MODE": "live"})


def test_settings_reject_enabled_live_trading_flag() -> None:
    with pytest.raises(ConfigError, match="live trading"):
        Settings.from_env({"LIVE_TRADING_ENABLED": "true"})


@pytest.mark.parametrize("raw_value", ["maybe", "2", "enabled"])
def test_settings_reject_invalid_live_trading_bool(raw_value: str) -> None:
    with pytest.raises(ConfigError, match="LIVE_TRADING_ENABLED"):
        Settings.from_env({"LIVE_TRADING_ENABLED": raw_value})


def test_settings_reject_live_ibkr_account_mode() -> None:
    with pytest.raises(ConfigError, match="IBKR_ACCOUNT_MODE"):
        Settings.from_env({"IBKR_ACCOUNT_MODE": "live"})


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.12", "broker.example.com"])
def test_settings_reject_non_local_ibkr_host(host: str) -> None:
    with pytest.raises(ConfigError, match="IBKR_HOST"):
        Settings.from_env({"IBKR_HOST": host})


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_settings_reject_invalid_ibkr_port(port: str) -> None:
    with pytest.raises(ConfigError, match="IBKR_PORT"):
        Settings.from_env({"IBKR_PORT": port})


def test_settings_reject_production_paper_mode_without_explicit_simulation() -> None:
    with pytest.raises(ConfigError, match="APP_ENV=production"):
        Settings.from_env({"APP_ENV": "production", "APP_MODE": "paper"})


def test_settings_allow_production_only_for_simulation_mode() -> None:
    settings = Settings.from_env({"APP_ENV": "production", "APP_MODE": "simulation"})

    assert settings.app_env == "production"
    assert settings.app_mode == "simulation"
