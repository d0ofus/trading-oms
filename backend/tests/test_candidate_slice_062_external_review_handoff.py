from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from trading_oms_backend.independent_review_packet import (
    build_independent_review_packet,
    scan_for_unsafe_packet_content,
    verify_independent_review_packet,
)

ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = ROOT / "review" / "candidate-062"
SPEC_PATH = REVIEW_DIR / "spec.json"
PACKET_PATH = REVIEW_DIR / "packet.json"
DIGEST_PATH = REVIEW_DIR / "packet.sha256"
GUIDE_PATH = REVIEW_DIR / "REVIEW_GUIDE.md"
RESPONSE_PATH = REVIEW_DIR / "REVIEW_RESPONSE_TEMPLATE.md"

BASELINE_COMMIT = "eafc3939f2c5cdc2a7fe09280381395e648bc28d"
BASELINE_TREE = "d1074dd86dc6b03ce6683cf90d9f2bce7a2da723"
BASELINE_SUBJECT = "Plan Candidate Slice 062 IBKR paper connector (#43)"
PLAN_PATH = "docs/execplans/candidate-slice-062-ibkr-paper-connector-execplan.md"
PLAN_BLOB = "e72d53b9ca85744809e91a3fdff97c42e41bfa7a"
PLAN_SHA256 = "b76575eaf048c13b91bc18ecb778c767b11d66da428d42ec9710ddfc1fade145"

EXPECTED_FINDINGS = {
    "c062_001_sdk_provenance",
    "c062_002_paper_proof_and_account_ambiguity",
    "c062_003_client_order_identity_and_outbox",
    "c062_004_callbacks_and_protection",
    "c062_005_reconnect_and_reconciliation",
    "c062_006_network_and_private_data",
    "c062_007_alert_and_emergency_response",
    "c062_008_independent_review_absent",
}

EXPECTED_EVIDENCE_CATEGORIES = {
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


def test_handoff_is_bound_to_exact_merged_candidate_062_plan() -> None:
    packet = _packet()

    assert packet["baseline"] == {
        "commit_sha": BASELINE_COMMIT,
        "subject": BASELINE_SUBJECT,
        "tree_sha": BASELINE_TREE,
    }

    source_entries = {entry["path"]: entry for entry in packet["manifests"]["source"]["entries"]}
    plan = source_entries[PLAN_PATH]
    assert plan["git_blob_sha"] == PLAN_BLOB
    assert plan["sha256"] == PLAN_SHA256

    evidence_entries = {
        entry["path"]: entry for entry in packet["manifests"]["evidence"]["documents"]
    }
    assert evidence_entries[PLAN_PATH]["git_blob_sha"] == PLAN_BLOB
    assert evidence_entries[PLAN_PATH]["sha256"] == PLAN_SHA256
    assert evidence_entries[PLAN_PATH]["review_status"] == "pending_independent_review"


def test_handoff_packet_is_deterministic_and_checked_in_identity_verifies() -> None:
    first = build_independent_review_packet(ROOT, SPEC_PATH)
    second = build_independent_review_packet(ROOT, SPEC_PATH)

    assert first.to_stable_json() == second.to_stable_json()
    assert first.sha256() == second.sha256()
    assert PACKET_PATH.read_text(encoding="utf-8") == first.to_stable_json() + "\n"
    assert DIGEST_PATH.read_text(encoding="ascii") == (f"{first.sha256()}  {PACKET_PATH.name}\n")
    assert verify_independent_review_packet(ROOT, PACKET_PATH, DIGEST_PATH) == {
        "baseline_commit": BASELINE_COMMIT,
        "baseline_tree": BASELINE_TREE,
        "packet_sha256": first.sha256(),
        "result": "verified_local_artifact_identity",
        "review_status": "not_independently_reviewed",
    }


def test_byte_sensitive_review_artifacts_are_pinned_to_lf() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert "review/**/*.json text eol=lf" in attributes
    assert "review/**/*.sha256 text eol=lf" in attributes


def test_handoff_keeps_all_readiness_and_external_review_gates_closed() -> None:
    packet = _packet()

    assert packet["review_status"] == "not_independently_reviewed"
    assert packet["readiness"] == {
        "blocking_evidence_count": 14,
        "decision": "no_go",
        "external_review_evidence": "missing",
        "result": "not_ready",
        "verified_evidence_count": 0,
    }

    unresolved = packet["unresolved_evidence"]
    assert unresolved["blocking_count"] == 14
    assert unresolved["item_count"] == 14
    assert unresolved["verified_count"] == 0
    assert {item["category"] for item in unresolved["items"]} == (EXPECTED_EVIDENCE_CATEGORIES)
    assert all(item["status"] != "verified" for item in unresolved["items"])
    external = next(item for item in unresolved["items"] if item["category"] == "external_review")
    assert external["status"] == "missing"


def test_handoff_exposes_every_blocking_p0_p1_design_finding() -> None:
    findings = _packet()["findings"]

    assert findings["finding_count"] == len(EXPECTED_FINDINGS)
    assert {item["finding_id"] for item in findings["items"]} == EXPECTED_FINDINGS
    assert all(item["severity"] in {"P0", "P1"} for item in findings["items"])
    assert all(item["blocking"] is True for item in findings["items"])
    assert all(item["resolution_state"] == "open" for item in findings["items"])
    assert all(
        item["owner_status"] in {"unassigned", "internal_owner_needed"}
        for item in findings["items"]
    )

    summaries = " ".join(item["summary"].lower() for item in findings["items"])
    for required_topic in (
        "10.48",
        "artifact",
        "license",
        "sha-256",
        "paper-session proof",
        "account ambiguity",
        "client id",
        "order-id",
        "durable outbox",
        "idempotency",
        "callback",
        "protection",
        "disconnect",
        "reconnect",
        "reconciliation",
        "local-only",
        "private data",
        "no-op alert",
        "emergency-stop",
        "architecture",
        "trading-safety",
        "security",
    ):
        assert required_topic in summaries


def test_review_guide_requires_attributable_three_discipline_response() -> None:
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    response = RESPONSE_PATH.read_text(encoding="utf-8")

    for exact_identity in (
        BASELINE_COMMIT,
        BASELINE_TREE,
        PLAN_PATH,
        PLAN_BLOB,
        PLAN_SHA256,
    ):
        assert exact_identity in guide

    for discipline in ("Architecture reviewer", "Trading-safety reviewer", "Security reviewer"):
        assert discipline in guide
        assert discipline in response

    for response_field in (
        "Reviewer identity",
        "Reviewer role",
        "Review date",
        "Reviewed scope",
        "Evidence examined",
        "Disposition",
        "Residual risk",
    ):
        assert response_field in response

    assert response.count("`pending`") >= 10
    assert "not independent-review evidence" in response
    assert "does not authorize Candidate 063" in response
    assert "not_ready" in guide
    assert "external review remains `missing`" in guide
    assert "all 14" in guide
    assert "zero" in guide


def test_candidate_063_gate_and_reproduction_steps_are_explicit() -> None:
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    required_gate_text = (
        "Candidate 063 remains blocked",
        "separate explicit human approval",
        "all three review disciplines",
        "every P0/P1 finding",
        "reviewed source changes",
        "python -m trading_oms_backend.independent_review_packet verify",
        "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\verify.ps1",
    )
    for text in required_gate_text:
        assert text in guide

    for topic_id in (
        "Q-SDK-01",
        "Q-PAPER-01",
        "Q-IDENTITY-01",
        "Q-OUTBOX-01",
        "Q-CALLBACK-01",
        "Q-PROTECTION-01",
        "Q-RESILIENCE-01",
        "Q-SECURITY-01",
    ):
        assert topic_id in guide


def test_complete_handoff_is_recursively_secret_and_private_data_scanned() -> None:
    handoff_files = sorted(path for path in REVIEW_DIR.rglob("*") if path.is_file())
    assert {path.name for path in handoff_files} == {
        "REVIEW_GUIDE.md",
        "REVIEW_RESPONSE_TEMPLATE.md",
        "packet.json",
        "packet.sha256",
        "spec.json",
    }

    for path in handoff_files:
        content = path.read_text(encoding="ascii" if path.suffix == ".sha256" else "utf-8")
        assert scan_for_unsafe_packet_content({"handoff_content": content}) == ()
        assert re.search(r"(?i)\b(?:du|u)\d{6,}\b", content) is None
        assert "https://" not in content
        assert "http://" not in content


def test_handoff_does_not_add_connector_or_runtime_capability() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")
    packet = PACKET_PATH.read_text(encoding="utf-8")
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    response = RESPONSE_PATH.read_text(encoding="utf-8")
    combined = "\n".join((spec, packet, guide, response)).lower()

    assert "no_ibkr_dependency_or_runtime_change" in combined
    assert "candidate 063 remains blocked" in guide.lower()
    assert "no broker contact" in guide.lower()
    assert "no live trading" in guide.lower()
    assert hashlib.sha256((ROOT / PLAN_PATH).read_bytes()).hexdigest() == PLAN_SHA256


def test_repository_docs_publish_handoff_without_claiming_external_review() -> None:
    docs = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/SECURITY_BASELINE.md", "docs/SLICES.md")
    }

    for content in docs.values():
        assert "review/candidate-062/REVIEW_GUIDE.md" in content
        assert "Candidate 063" in content
        assert "not_ready" in content

    combined = "\n".join(docs.values())
    assert "external-review evidence remains `missing`" in combined
    assert "all 14" in combined
    assert "zero" in combined
    assert "separate explicit" in combined
    assert "not independently reviewed" in combined


def _packet() -> dict[str, object]:
    return json.loads(PACKET_PATH.read_text(encoding="utf-8"))
