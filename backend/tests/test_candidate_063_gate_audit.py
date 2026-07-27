from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "CANDIDATE_063_GATE_AUDIT.md"
SLICES = ROOT / "docs" / "SLICES.md"

AUTHORITATIVE_MAIN = "197009c2af0146d96faad95468785a422a0aa5fe"
AUTHORITATIVE_TREE = "06a174b7b9109c6662e0147dea8fce308d3a9663"
PACKET_SHA256 = "420f8223d34b57bd7ac0f918faa1ac9110650a0ec49c9e9b3fa2ede5f7f2894b"
PLAN_SHA256 = "b76575eaf048c13b91bc18ecb778c767b11d66da428d42ec9710ddfc1fade145"

FINDING_IDS = {
    "c062_001_sdk_provenance",
    "c062_002_paper_proof_and_account_ambiguity",
    "c062_003_client_order_identity_and_outbox",
    "c062_004_callbacks_and_protection",
    "c062_005_reconnect_and_reconciliation",
    "c062_006_network_and_private_data",
    "c062_007_alert_and_emergency_response",
    "c062_008_independent_review_absent",
}

UNRESOLVED_CATEGORIES = {
    "authentication_authorization",
    "audit_retention",
    "backup_restore",
    "emergency_stop",
    "external_review",
    "incident_response",
    "live_readiness",
    "network_exposure",
    "observability",
    "operator_signoff",
    "paper_trading_history",
    "reconciliation",
    "rollback",
    "secret_management",
}


def test_gate_audit_is_bound_to_the_authoritative_merged_baseline() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for identity in (
        AUTHORITATIVE_MAIN,
        AUTHORITATIVE_TREE,
        PACKET_SHA256,
        PLAN_SHA256,
    ):
        assert identity in text

    assert "PR 54" in text
    assert "Candidate 063 decision: `blocked` / `no_go`" in text


def test_gate_audit_accounts_for_every_open_finding_and_unresolved_category() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for finding_id in FINDING_IDS:
        assert finding_id in text
    for category in UNRESOLVED_CATEGORIES:
        assert f"`{category}`" in text

    assert "eight open blocking P0/P1 findings" in text
    assert "fourteen unresolved evidence categories" in text
    assert "zero verified evidence categories" in text


def test_gate_audit_requires_independent_review_and_stops_before_connector_work() -> None:
    text = REPORT.read_text(encoding="utf-8")
    normalized = " ".join(text.split()).casefold()

    required = (
        "architecture reviewer",
        "trading-safety reviewer",
        "security reviewer",
        "separate explicit human approval",
        "no ibkr dependency",
        "no connector",
        "no broker contact",
        "no paper lab",
        "live trading remains disabled",
    )
    for phrase in required:
        assert phrase.casefold() in normalized

    assert (
        "a merge, green ci, internal self-review, or completed template cannot open the gate"
        in (normalized)
    )


def test_gate_audit_candidate_is_documented_as_review_only() -> None:
    slices = SLICES.read_text(encoding="utf-8")
    match = re.search(
        r"## Documentation-only candidate - Candidate 063 entry-gate audit.*?(?=\n---\n|\Z)",
        slices,
        flags=re.DOTALL,
    )

    assert match is not None
    section = match.group(0)
    assert "status: `ready_for_human_review`" in section
    assert "branch: `candidate-slice-063-entry-gate-audit`" in section
    assert "Candidate 063 remains blocked" in section
    assert "No IBKR dependency, connector, broker contact, or paper lab is added." in section
