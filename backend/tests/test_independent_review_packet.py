from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from trading_oms_backend import independent_review_packet
from trading_oms_backend.independent_review_packet import (
    ReviewPacketError,
    build_independent_review_packet,
    scan_for_unsafe_packet_content,
    verify_independent_review_packet,
    write_independent_review_packet,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "review" / "candidate-061" / "spec.json"
PACKET_PATH = ROOT / "review" / "candidate-061" / "packet.json"
DIGEST_PATH = ROOT / "review" / "candidate-061" / "packet.sha256"
GUIDE_PATH = ROOT / "review" / "candidate-061" / "REVIEW_GUIDE.md"
BASELINE_COMMIT = "2db249f7b7c239a7f09885d17f30cc8ba587afc0"
BASELINE_TREE = "ae4caa823c99cf50a5a6f6cad744886d310b4c5e"

REVIEW_SCOPE_IDS = {
    "architecture_failure_containment",
    "dependency_supply_chain",
    "identity_secrets_network",
    "journal_auditability",
    "oms_approval_protection_reconciliation_emergency",
    "operational_readiness",
    "provenance_product_claims",
    "trading_safety_risk",
}

EVIDENCE_CATEGORIES = {
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


@pytest.fixture
def review_output_paths() -> Iterator[tuple[Path, Path]]:
    temp_root = ROOT / "backend" / ".test-tmp"
    temp_root.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=temp_root) as temp_dir:
        yield Path(temp_dir) / "packet.json", Path(temp_dir) / "packet.sha256"


def test_packet_is_bound_to_complete_baseline_git_tree() -> None:
    packet = build_independent_review_packet(ROOT, SPEC_PATH).to_json_dict()
    baseline = packet["baseline"]
    source = packet["manifests"]["source"]

    assert baseline == {
        "commit_sha": BASELINE_COMMIT,
        "tree_sha": BASELINE_TREE,
        "subject": "Harden evidence provenance and readiness (#41)",
    }
    assert packet["review_status"] == "not_independently_reviewed"
    assert packet["readiness"] == {
        "blocking_evidence_count": 14,
        "decision": "no_go",
        "external_review_evidence": "missing",
        "result": "not_ready",
        "verified_evidence_count": 0,
    }
    assert [entry["path"] for entry in source["entries"]] == sorted(
        entry["path"] for entry in source["entries"]
    )
    assert source["entry_count"] == len(_baseline_paths())
    assert {entry["path"] for entry in source["entries"]} == set(_baseline_paths())
    assert all(len(entry["sha256"]) == 64 for entry in source["entries"])
    _assert_manifest_digest(source)


def test_packet_contains_deterministic_dependency_test_verification_and_evidence_manifests() -> (
    None
):
    packet = build_independent_review_packet(ROOT, SPEC_PATH).to_json_dict()
    manifests = packet["manifests"]

    assert set(manifests) == {"dependencies", "evidence", "source", "tests", "verification"}
    for manifest in manifests.values():
        _assert_manifest_digest(manifest)

    dependency_paths = {entry["path"] for entry in manifests["dependencies"]["files"]}
    assert dependency_paths == {
        "backend/pyproject.toml",
        "backend/requirements-dev.txt",
        "frontend/package-lock.json",
        "frontend/package.json",
    }
    assert manifests["dependencies"]["python_lock_status"] == "unlocked_constraints"
    assert manifests["dependencies"]["npm_lock_status"] == "lockfile_present"
    assert manifests["dependencies"]["packages"]
    assert all(
        set(package) == {"constraint", "ecosystem", "name", "resolved_version"}
        for package in manifests["dependencies"]["packages"]
    )

    test_paths = {entry["path"] for entry in manifests["tests"]["files"]}
    assert "backend/tests/test_risk_engine.py" in test_paths
    assert "frontend/src/App.test.tsx" in test_paths
    assert manifests["tests"]["file_count"] == len(test_paths)
    assert manifests["tests"]["definition_count"] > 0

    verification = manifests["verification"]
    assert verification["evidence_level"] == "local_self_recorded"
    assert verification["result"] == "passed"
    assert verification["backend_tests"] == {"collected": 555, "passed": 555}
    assert verification["frontend_tests"] == {"files": 15, "passed": 60}
    assert verification["resilience_tests"] == {"collected": 4, "passed": 4}
    assert verification["limitations"]

    evidence_paths = {entry["path"] for entry in manifests["evidence"]["documents"]}
    assert {
        "AGENTS.md",
        "docs/CONTROLLED_PAPER_PRODUCTION_ROLLOUT_CHECKLIST.md",
        "docs/EVIDENCE_PROVENANCE.md",
        "docs/POST_SLICE_059_REVIEW.md",
        "docs/SECURITY_BASELINE.md",
    }.issubset(evidence_paths)
    assert all(
        entry["review_status"] == "pending_independent_review"
        for entry in manifests["evidence"]["documents"]
    )


def test_packet_exposes_scope_traceability_open_findings_and_all_unresolved_evidence() -> None:
    packet = build_independent_review_packet(ROOT, SPEC_PATH).to_json_dict()

    assert {item["scope_id"] for item in packet["review_scope"]} == REVIEW_SCOPE_IDS
    assert packet["traceability"]["control_count"] == len(packet["traceability"]["controls"])
    assert packet["traceability"]["controls"]
    _assert_manifest_digest(packet["traceability"])

    findings = packet["findings"]
    assert findings["finding_count"] == len(findings["items"])
    assert findings["items"]
    assert all(
        {
            "blocking",
            "evidence_references",
            "finding_id",
            "owner_status",
            "resolution_state",
            "severity",
            "summary",
        }.issubset(item)
        for item in findings["items"]
    )
    assert all(item["resolution_state"] == "open" for item in findings["items"])
    assert all(item["blocking"] for item in findings["items"] if item["severity"] in {"P0", "P1"})
    _assert_manifest_digest(findings)

    unresolved = packet["unresolved_evidence"]
    assert unresolved["item_count"] == 14
    assert unresolved["blocking_count"] == 14
    assert unresolved["verified_count"] == 0
    assert {item["category"] for item in unresolved["items"]} == EVIDENCE_CATEGORIES
    assert [item["status"] for item in unresolved["items"]].count("missing") == 6
    assert [item["status"] for item in unresolved["items"]].count("unverified") == 8
    assert (
        next(item for item in unresolved["items"] if item["category"] == "external_review")[
            "status"
        ]
        == "missing"
    )
    _assert_manifest_digest(unresolved)


@pytest.mark.parametrize(
    "unsafe_value",
    (
        {"api_key": "redacted"},
        {"summary": "token=redacted"},
        {"account_id": "redacted"},
        {"private_value": "redacted"},
        {"reference": "https://unsafe.invalid/review"},
        {"broker_host": "localhost"},
        {"submit_order": True},
        {"live_trading_enabled": True},
        {"broker_transport_allowed": True},
    ),
)
def test_packet_scanner_rejects_unsafe_content(unsafe_value: object) -> None:
    findings = scan_for_unsafe_packet_content(unsafe_value)

    assert findings


def test_packet_generation_and_verification_are_deterministic(
    review_output_paths: tuple[Path, Path],
) -> None:
    output_path, digest_path = review_output_paths
    first = build_independent_review_packet(ROOT, SPEC_PATH)
    second = build_independent_review_packet(ROOT, SPEC_PATH)

    assert first.to_stable_json() == second.to_stable_json()
    assert first.sha256() == second.sha256()
    write_independent_review_packet(first, output_path, digest_path)

    assert output_path.read_text(encoding="utf-8") == first.to_stable_json() + "\n"
    assert digest_path.read_text(encoding="ascii") == f"{first.sha256()}  packet.json\n"
    result = verify_independent_review_packet(ROOT, output_path, digest_path)
    assert result == {
        "baseline_commit": BASELINE_COMMIT,
        "baseline_tree": BASELINE_TREE,
        "packet_sha256": first.sha256(),
        "result": "verified_local_artifact_identity",
        "review_status": "not_independently_reviewed",
    }


def test_packet_verification_rejects_tampering(
    review_output_paths: tuple[Path, Path],
) -> None:
    output_path, digest_path = review_output_paths
    packet = build_independent_review_packet(ROOT, SPEC_PATH)
    write_independent_review_packet(packet, output_path, digest_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    payload["review_status"] = "independently_reviewed"
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ReviewPacketError, match="packet digest does not match sidecar"):
        verify_independent_review_packet(ROOT, output_path, digest_path)


def test_checked_in_packet_matches_generator_and_human_guide() -> None:
    expected = build_independent_review_packet(ROOT, SPEC_PATH)

    assert PACKET_PATH.read_text(encoding="utf-8") == expected.to_stable_json() + "\n"
    assert DIGEST_PATH.read_text(encoding="ascii") == f"{expected.sha256()}  packet.json\n"
    assert verify_independent_review_packet(ROOT, PACKET_PATH, DIGEST_PATH)["result"] == (
        "verified_local_artifact_identity"
    )

    guide = GUIDE_PATH.read_text(encoding="utf-8")
    required_text = (
        BASELINE_COMMIT,
        BASELINE_TREE,
        "not independently reviewed",
        "External-review evidence remains missing",
        "Current result: `not_ready`",
        "Current decision: `no_go`",
        "does not authorize",
        "Candidate Slice 062",
    )
    for text in required_text:
        assert text in guide


def test_packet_module_has_no_network_api_broker_or_external_delivery_integration() -> None:
    source = inspect.getsource(independent_review_packet).lower()
    forbidden_source = (
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import urllib",
        "fastapi",
        "@app.",
        "ibapi",
        "ib_insync",
        "place_order(",
        "submit_order(",
        "connect(",
        "upload(",
    )

    for token in forbidden_source:
        assert token not in source


def _assert_manifest_digest(manifest: dict[str, object]) -> None:
    content = {key: value for key, value in manifest.items() if key != "content_sha256"}
    assert manifest["content_sha256"] == _sha256_json(content)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _baseline_paths() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", BASELINE_COMMIT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(path for path in result.stdout.splitlines() if path)
