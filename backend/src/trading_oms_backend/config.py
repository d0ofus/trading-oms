from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ


class ConfigError(ValueError):
    """Raised when configuration would violate the safety baseline."""


def _read_bool(name: str, raw_value: str | None, default: bool) -> bool:
    if raw_value is None or raw_value == "":
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ConfigError(f"{name} must be a boolean value")


@dataclass(frozen=True)
class Settings:
    app_mode: str = "paper"
    live_trading_enabled: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = environ if env is None else env
        app_mode = source.get("APP_MODE", "paper").strip().lower()
        live_trading_enabled = _read_bool(
            "LIVE_TRADING_ENABLED",
            source.get("LIVE_TRADING_ENABLED"),
            default=False,
        )

        settings = cls(app_mode=app_mode, live_trading_enabled=live_trading_enabled)
        settings.validate_safety()
        return settings

    def validate_safety(self) -> None:
        if self.app_mode not in {"paper", "simulation"}:
            raise ConfigError("APP_MODE must be paper or simulation")
        if self.live_trading_enabled:
            raise ConfigError("live trading must remain disabled")


def get_settings() -> Settings:
    return Settings.from_env()
