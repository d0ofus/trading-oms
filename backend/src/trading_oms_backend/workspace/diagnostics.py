"""Safe, structured diagnostics. Never retain exception text or broker free text."""

from pathlib import Path


def broker_diagnostic(code, message=""):
    lower = message.lower()
    reason = {
        2119: "data_connecting",
        2104: "data_connected",
        2106: "history_connected",
        321: "request_validation",
        354: "market_data_permission",
        10189: "market_data_permission",
    }.get(code, "broker_request_failed")
    if code == 321 and ("read-only" in lower or "read only" in lower):
        reason = "api_read_only"
    details = {
        "data_connecting": "Gateway is connecting to a market-data service.",
        "api_read_only": "Gateway rejected a request because API read-only mode is enabled. "
        "Keep entries disarmed, disable Read-Only API in the paper Gateway, then reconcile again.",
        "request_validation": "Gateway rejected an API request during validation. "
        "Recheck the affected operation and inspect its diagnostic reference.",
        "market_data_permission": "The broker has not granted this market-data request. "
        "Check the paper login's data entitlement.",
    }
    return {
        "reason": reason,
        "detail": details.get(
            reason,
            f"Gateway reported code {code}. "
            "Recheck the affected operation before entry authorization.",
        ),
    }


def exception_diagnostic(exc, operation):
    frames = []
    tb = exc.__traceback__
    while tb:
        code = tb.tb_frame.f_code
        frames.append(
            {"file": Path(code.co_filename).name, "function": code.co_name, "line": tb.tb_lineno}
        )
        tb = tb.tb_next
    return {"exception": type(exc).__name__, "operation": operation, "frames": frames[-12:]}
