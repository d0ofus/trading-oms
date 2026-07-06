from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ


class ConfigError(ValueError):
    """Raised when configuration would violate the safety baseline."""


LOCAL_IBKR_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _read_choice(name: str, raw_value: str | None, default: str, allowed: set[str]) -> str:
    value = default if raw_value is None or raw_value == "" else raw_value.strip().lower()
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ConfigError(f"{name} must be one of: {allowed_values}")
    return value


def _read_bool(name: str, raw_value: str | None, default: bool) -> bool:
    if raw_value is None or raw_value == "":
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ConfigError(f"{name} must be a boolean value")


def _read_port(name: str, raw_value: str | None, default: int) -> int:
    if raw_value is None or raw_value == "":
        return default

    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer TCP port") from exc

    if not 1 <= port <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535")

    return port


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    app_mode: str = "paper"
    live_trading_enabled: bool = False
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_account_mode: str = "paper"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = environ if env is None else env
        app_env = _read_choice(
            "APP_ENV",
            source.get("APP_ENV"),
            default="development",
            allowed={"development", "test", "production"},
        )
        app_mode = _read_choice(
            "APP_MODE",
            source.get("APP_MODE"),
            default="paper",
            allowed={"paper", "simulation"},
        )
        live_trading_enabled = _read_bool(
            "LIVE_TRADING_ENABLED",
            source.get("LIVE_TRADING_ENABLED"),
            default=False,
        )
        ibkr_host = source.get("IBKR_HOST", "127.0.0.1").strip().lower()
        ibkr_port = _read_port("IBKR_PORT", source.get("IBKR_PORT"), default=7497)
        ibkr_account_mode = _read_choice(
            "IBKR_ACCOUNT_MODE",
            source.get("IBKR_ACCOUNT_MODE"),
            default="paper",
            allowed={"paper"},
        )

        settings = cls(
            app_env=app_env,
            app_mode=app_mode,
            live_trading_enabled=live_trading_enabled,
            ibkr_host=ibkr_host,
            ibkr_port=ibkr_port,
            ibkr_account_mode=ibkr_account_mode,
        )
        settings.validate_safety()
        return settings

    def validate_safety(self) -> None:
        if self.live_trading_enabled:
            raise ConfigError("live trading must remain disabled")
        if self.app_env == "production" and self.app_mode != "simulation":
            raise ConfigError("APP_ENV=production requires APP_MODE=simulation")
        if self.ibkr_host not in LOCAL_IBKR_HOSTS:
            raise ConfigError("IBKR_HOST must be localhost-only")


def get_settings() -> Settings:
    return Settings.from_env()
