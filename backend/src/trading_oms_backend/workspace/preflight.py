from __future__ import annotations

import json
import os
import socket
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .broker import SDK_VERSION
from .verification import verified


def main():
    checks = []
    checks.append(
        {
            "check": "Verified application build",
            "passed": verified(),
            "detail": "Run scripts/verify.ps1 for the current source and production bundle.",
        }
    )
    try:
        sdk = version("ibapi")
    except PackageNotFoundError:
        sdk = None
    checks.append(
        {
            "check": "Official Python API version",
            "passed": sdk == SDK_VERSION,
            "detail": sdk or "Run scripts/install-paper-sdk.ps1",
        }
    )
    try:
        protobuf_ok = version("protobuf") == "5.29.6"
    except PackageNotFoundError:
        protobuf_ok = False
    checks.append(
        {
            "check": "Patched Protobuf runtime",
            "passed": protobuf_ok,
            "detail": "The SDK installer applies a packaging-only 5.29.6 pin.",
        }
    )
    try:
        with socket.create_connection(("127.0.0.1", 4002), timeout=2):
            available = True
    except OSError:
        available = False
    checks.append(
        {
            "check": "Local paper Gateway endpoint",
            "passed": available,
            "detail": "TCP only; login, entitlements and reconciliation need workspace checks.",
        }
    )
    frontend = Path(__file__).resolve().parents[4] / "frontend" / "dist" / "index.html"
    checks.append(
        {
            "check": "Built frontend",
            "passed": frontend.exists(),
            "detail": "npm --prefix frontend run build",
        }
    )
    checks.append(
        {
            "check": "Windows credential storage",
            "passed": os.name == "nt",
            "detail": "Windows Credential Manager is required for monitoring.",
        }
    )
    print(
        json.dumps({"mode": "paper", "broker_orders_submitted": False, "checks": checks}, indent=2)
    )
    raise SystemExit(0 if all(c["passed"] for c in checks) else 1)


if __name__ == "__main__":
    main()
