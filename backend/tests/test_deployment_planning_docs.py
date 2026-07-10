import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN_DOC = ROOT / "docs" / "DEPLOYMENT_AND_SECRETS_MANAGEMENT_PLAN.md"
SLICES_DOC = ROOT / "docs" / "SLICES.md"
SECURITY_DOC = ROOT / "docs" / "SECURITY_BASELINE.md"
EXECPLAN_DOC = ROOT / "docs" / "execplans" / "slice-053-deployment-secrets-management-plan.md"
EMERGENCY_STOP_DOC = ROOT / "docs" / "EMERGENCY_STOP.md"
OPERATIONS_CONTROLS_DOC = ROOT / "docs" / "OPERATIONS_CONTROLS.md"


def test_slice_053_deployment_and_secrets_plan_preserves_hard_stops() -> None:
    for path in (PLAN_DOC, SECURITY_DOC, EXECPLAN_DOC, EMERGENCY_STOP_DOC, OPERATIONS_CONTROLS_DOC):
        assert path.exists(), f"{path.relative_to(ROOT)} is missing"

    plan_text = PLAN_DOC.read_text(encoding="utf-8")
    security_text = SECURITY_DOC.read_text(encoding="utf-8")
    emergency_stop_text = EMERGENCY_STOP_DOC.read_text(encoding="utf-8")
    operations_text = OPERATIONS_CONTROLS_DOC.read_text(encoding="utf-8")
    combined = f"{plan_text}\n{security_text}\n{emergency_stop_text}\n{operations_text}"

    required_phrases = [
        "Planning only: this document does not approve production rollout.",
        "Live trading remains disabled.",
        "No live broker order path may be introduced.",
        "No real broker credentials, account identifiers, passwords, "
        "certificates, private keys, tokens, or secrets",
        "IBKR TWS or Gateway API ports must never be exposed to the public internet.",
        "Production-like paper operation requires separate explicit human "
        "approval and external review.",
        "Slice 054 adds a local operator authentication and authorization foundation.",
        "Slice 055 hardens",
        "Slice 056 adds a local emergency stop",
        "No broker-side liquidation, flatten, live cancel, live route, "
        "live submit, or live transmit",
        "Simulation approval requires the dedicated local `approver` role.",
        "Rollback planning must preserve the append-only audit trail.",
        "Backup and restore planning must protect journal and persistence "
        "data without exporting secrets.",
        "Slice 057 adds read-only local operating-control visibility",
        "Destructive retention is disabled.",
        "external storage not configured",
        "Incident response does not add broker-side liquidation",
    ]
    for phrase in required_phrases:
        assert phrase in combined


def test_slice_053_plan_does_not_document_secret_values_or_live_enablement() -> None:
    plan_text = PLAN_DOC.read_text(encoding="utf-8")
    security_text = SECURITY_DOC.read_text(encoding="utf-8")
    combined = f"{plan_text}\n{security_text}"

    forbidden_patterns = [
        r"APP_MODE\s*=\s*live",
        r"LIVE_TRADING_ENABLED\s*=\s*true",
        r"IBKR_ACCOUNT_MODE\s*=\s*live",
        r"live trading approved",
        r"production rollout approved",
        r"public ibkr ports are allowed",
        r"real account id",
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, combined, flags=re.IGNORECASE) is None


def test_slice_057_is_ready_and_later_slices_remain_not_started() -> None:
    slices_text = SLICES_DOC.read_text(encoding="utf-8")

    assert _slice_status(slices_text, "053") == "ready_for_human_review"
    assert _slice_status(slices_text, "054") == "ready_for_human_review"
    assert _slice_status(slices_text, "055") == "ready_for_human_review"
    assert _slice_status(slices_text, "056") == "ready_for_human_review"
    assert _slice_status(slices_text, "057") == "ready_for_human_review"
    for slice_id in ("058", "059"):
        assert _slice_status(slices_text, slice_id) == "not_started"


def _slice_status(text: str, slice_id: str) -> str:
    match = re.search(
        rf"## Slice {slice_id} - .*?(?=\n---\n|\Z)",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, f"Slice {slice_id} section is missing"
    status_match = re.search(r"status: `([^`]+)`", match.group(0))
    assert status_match is not None, f"Slice {slice_id} status is missing"
    return status_match.group(1)
