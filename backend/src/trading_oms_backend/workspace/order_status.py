"""Conservative projection of asynchronous broker status observations."""

STATES = {
    "ApiPending": "dispatching",
    "PendingSubmit": "dispatching",
    "PreSubmitted": "working",
    "Submitted": "working",
    "PendingCancel": "cancel_pending",
    "Cancelled": "cancelled",
    "ApiCancelled": "cancelled",
    "Filled": "filled",
    "Inactive": "unknown",
    "Rejected": "rejected",
}
PENDING = {"ApiPending", "PendingSubmit"}
WORKING = {"PreSubmitted", "Submitted"}
TERMINAL = {"Cancelled", "ApiCancelled", "Filled", "Rejected"}
CANCEL_REASONS = {
    "fx_protection_resize": "Cancelled FX protection before reconciling "
    "its replacement quantity or stop",
    "fx_exit_requested": "Cancelled the competing FX order before a serialized exit or limit retry",
    "partial_fill": "Cancelled the unfilled remainder after a confirmed partial fill",
    "operator": "Cancelled by operator request",
    "entry_timeout": "Cancelled after the entry acknowledgment/execution deadline",
    "run_disarmed": "Cancelled because the run was disarmed",
    "emergency_stop": "Cancelled because emergency stop was activated",
    "incident_restriction": "Cancelled by the application because an incident restricted entries",
}


def project_status(old, observation):
    """Retain details while preventing a late callback from erasing stronger evidence."""
    previous, incoming = old.get("status"), observation.get("status", "")
    merged = {**old, **{k: v for k, v in observation.items() if v is not None}}
    if old.get("permanent_id") and not observation.get("permanent_id"):
        merged["permanent_id"] = old["permanent_id"]
    disposition = "applied"
    if (
        previous == "Rejected"
        and old.get("rejection_code") == 10318
        and incoming in {"Cancelled", "ApiCancelled"}
    ):
        disposition = "late_terminal"
    elif (
        previous in {"Cancelled", "ApiCancelled"}
        and incoming == "Rejected"
        and old.get("rejection_code") in {201, 10318}
    ):
        disposition = "late_rejection"
    elif incoming in PENDING and previous in WORKING | TERMINAL | {"PendingCancel"}:
        disposition = "late_pending"
    elif incoming == "PendingCancel" and previous in TERMINAL:
        disposition = "late_pending"
    elif previous == "Submitted" and incoming == "PreSubmitted":
        disposition = "late_pending"
    elif previous in TERMINAL and incoming in WORKING:
        disposition = "conflict"
    elif previous == "Filled" and incoming in TERMINAL - {"Filled"}:
        disposition = "late_terminal"
    elif previous in TERMINAL and (incoming not in STATES or incoming == "Inactive"):
        disposition = "conflict"
    if disposition != "applied":
        for key in ("status", "filled", "remaining", "average"):
            if key in old:
                merged[key] = old[key]
            else:
                merged.pop(key, None)
    if disposition == "conflict":
        merged["status_conflict"] = True
    elif observation.get("completed") and incoming in TERMINAL and disposition == "applied":
        # Fresh completed-order evidence can resolve the projection, but the incident
        # still requires complete reconciliation and explicit recovery acknowledgment.
        merged["status_conflict"] = False
    return merged, disposition
