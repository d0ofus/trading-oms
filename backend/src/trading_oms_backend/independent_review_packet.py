from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class ReviewPacketError(ValueError):
    """Raised when review-packet identity or safety validation fails."""


GENERATOR_PATH = "backend/src/trading_oms_backend/independent_review_packet.py"
DEPENDENCY_PATHS = (
    "backend/pyproject.toml",
    "backend/requirements-dev.txt",
    "frontend/package-lock.json",
    "frontend/package.json",
)
REQUIRED_SPEC_KEYS = {
    "baseline",
    "baseline_verification",
    "evidence_documents",
    "findings",
    "packet_id",
    "reproducible_commands",
    "review_scope",
    "schema_version",
    "traceability",
    "unresolved_evidence",
}
REQUIRED_SCOPE_IDS = {
    "architecture_failure_containment",
    "dependency_supply_chain",
    "identity_secrets_network",
    "journal_auditability",
    "oms_approval_protection_reconciliation_emergency",
    "operational_readiness",
    "provenance_product_claims",
    "trading_safety_risk",
}
REQUIRED_EVIDENCE_CATEGORIES = {
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
EVIDENCE_STATUSES = {"verified", "missing", "unverified", "expired", "contradictory"}
SECRET_KEY_TOKENS = {
    "api_key",
    "apikey",
    "authorization",
    "certificate",
    "credential",
    "password",
    "private_key",
    "private_value",
    "secret",
    "token",
}
FORBIDDEN_KEYS = {
    "account_id",
    "account_identifier",
    "broker_host",
    "broker_port",
    "callback_url",
    "connect_url",
    "place_order",
    "place_order_url",
    "route_order",
    "route_url",
    "submit_order",
    "submit_url",
    "transmit_order",
    "transmit_url",
}
FALSE_ONLY_KEYS = {
    "broker_transport_allowed",
    "external_delivery_enabled",
    "live_trading_authorized",
    "live_trading_enabled",
    "production_operation_authorized",
    "rollout_authorized",
}
UNSAFE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:account[_-]?id|api[_-]?key|broker[_-]?(?:host|port)|credential|"
    r"password|private[_-]?(?:key|value)|secret|token)\s*[:=]"
)
UNSAFE_URL_PATTERN = re.compile(r"(?i)\b(?:file|ftp|https?|javascript)://")
FULL_GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class ReviewPacketFinding:
    path: str
    reason: str
    matched: str


@dataclass(frozen=True)
class IndependentReviewPacket:
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        normalized = _normalized_json_object(self.payload, "independent review packet")
        findings = scan_for_unsafe_packet_content(normalized)
        if findings:
            raise ReviewPacketError(_finding_message(findings))

    def to_json_dict(self) -> dict[str, Any]:
        return _normalized_json_object(self.payload, "independent review packet")

    def to_stable_json(self) -> str:
        return json.dumps(
            self.to_json_dict(),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )

    def sha256(self) -> str:
        return _sha256_bytes((self.to_stable_json() + "\n").encode("utf-8"))


def build_independent_review_packet(
    repository: str | Path,
    specification_path: str | Path,
) -> IndependentReviewPacket:
    repo = Path(repository).resolve()
    if not (repo / ".git").exists():
        raise ReviewPacketError("repository must contain local Git metadata")
    spec_path = _safe_repository_path(repo, specification_path, "specification_path")
    spec_bytes = spec_path.read_bytes()
    specification = _normalized_json_object(
        _load_json_bytes(spec_bytes, "packet specification"),
        "packet specification",
    )
    _validate_specification(specification)
    spec_findings = scan_for_unsafe_packet_content(specification)
    if spec_findings:
        raise ReviewPacketError(_finding_message(spec_findings))

    baseline = _validated_baseline(repo, specification["baseline"])
    source_manifest, baseline_blobs = _build_source_manifest(repo, baseline["commit_sha"])
    dependency_manifest = _build_dependency_manifest(baseline_blobs, source_manifest)
    test_manifest = _build_test_manifest(baseline_blobs, source_manifest)
    evidence_manifest = _build_evidence_manifest(
        specification["evidence_documents"],
        source_manifest,
    )
    verification_manifest = _digest_section(
        _validated_verification(specification["baseline_verification"])
    )
    review_scope = _validated_review_scope(specification["review_scope"])
    traceability = _digest_section(
        _validated_traceability(specification["traceability"], review_scope)
    )
    findings = _digest_section(_validated_findings(specification["findings"]))
    unresolved = _digest_section(
        _validated_unresolved_evidence(specification["unresolved_evidence"])
    )
    readiness = _readiness_from_unresolved(unresolved)
    reproducible_commands = _validated_string_list(
        specification["reproducible_commands"],
        "reproducible_commands",
    )
    generator_path = _safe_repository_path(repo, GENERATOR_PATH, "generator_path")
    relative_spec_path = spec_path.relative_to(repo).as_posix()

    payload: dict[str, Any] = {
        "schema_version": 1,
        "packet_type": "independent_review_packet",
        "packet_id": _validated_identifier(specification["packet_id"], "packet_id"),
        "review_status": "not_independently_reviewed",
        "independence_statement": (
            "Prepared internally for review; no independent reviewer has accepted this packet"
        ),
        "baseline": baseline,
        "tooling": {
            "generator_path": GENERATOR_PATH,
            "generator_sha256": _sha256_bytes(generator_path.read_bytes()),
            "specification_path": relative_spec_path,
            "specification_sha256": _sha256_bytes(spec_bytes),
        },
        "readiness": readiness,
        "review_scope": review_scope,
        "reproducible_commands": list(reproducible_commands),
        "manifests": {
            "source": source_manifest,
            "dependencies": dependency_manifest,
            "tests": test_manifest,
            "verification": verification_manifest,
            "evidence": evidence_manifest,
        },
        "traceability": traceability,
        "findings": findings,
        "unresolved_evidence": unresolved,
    }
    safety_findings = scan_for_unsafe_packet_content(payload)
    if safety_findings:
        raise ReviewPacketError(_finding_message(safety_findings))
    payload["safety_scan"] = {
        "finding_count": 0,
        "policy": "candidate_061_packet_v1",
        "result": "passed",
    }
    return IndependentReviewPacket(payload)


def write_independent_review_packet(
    packet: IndependentReviewPacket,
    output_path: str | Path,
    digest_path: str | Path,
) -> None:
    if not isinstance(packet, IndependentReviewPacket):
        raise ReviewPacketError("packet must be IndependentReviewPacket")
    output = Path(output_path)
    digest = Path(digest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    digest.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(packet.to_stable_json() + "\n", encoding="utf-8", newline="\n")
    digest.write_text(
        f"{packet.sha256()}  {output.name}\n",
        encoding="ascii",
        newline="\n",
    )


def verify_independent_review_packet(
    repository: str | Path,
    packet_path: str | Path,
    digest_path: str | Path,
) -> dict[str, str]:
    repo = Path(repository).resolve()
    packet_file = Path(packet_path).resolve()
    digest_file = Path(digest_path).resolve()
    packet_bytes = packet_file.read_bytes()
    expected_sidecar = f"{_sha256_bytes(packet_bytes)}  {packet_file.name}\n"
    if digest_file.read_text(encoding="ascii") != expected_sidecar:
        raise ReviewPacketError("packet digest does not match sidecar")
    payload = _normalized_json_object(
        _load_json_bytes(packet_bytes, "independent review packet"),
        "independent review packet",
    )
    findings = scan_for_unsafe_packet_content(payload)
    if findings:
        raise ReviewPacketError(_finding_message(findings))
    tooling = _required_mapping(payload, "tooling", "packet")
    spec_relative = _validated_relative_path(
        tooling.get("specification_path"), "specification_path"
    )
    expected = build_independent_review_packet(repo, repo / spec_relative)
    if payload != expected.to_json_dict():
        raise ReviewPacketError("packet content does not match deterministic baseline rebuild")
    if packet_bytes != (expected.to_stable_json() + "\n").encode("utf-8"):
        raise ReviewPacketError("packet JSON is not in canonical stable form")
    baseline = _required_mapping(payload, "baseline", "packet")
    return {
        "baseline_commit": str(baseline["commit_sha"]),
        "baseline_tree": str(baseline["tree_sha"]),
        "packet_sha256": expected.sha256(),
        "result": "verified_local_artifact_identity",
        "review_status": str(payload["review_status"]),
    }


def scan_for_unsafe_packet_content(value: Any) -> tuple[ReviewPacketFinding, ...]:
    findings: list[ReviewPacketFinding] = []
    _scan_value(value, (), findings)
    return tuple(findings)


def _scan_value(
    value: Any,
    path: tuple[str, ...],
    findings: list[ReviewPacketFinding],
) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = _normalized_key(str(raw_key))
            _scan_key(key, nested, path, findings)
            _scan_value(nested, (*path, key), findings)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _scan_value(nested, (*path, str(index)), findings)
    elif isinstance(value, str):
        assignment_match = UNSAFE_ASSIGNMENT_PATTERN.search(value)
        if assignment_match:
            findings.append(
                ReviewPacketFinding(
                    path=_display_path(path),
                    reason="secret or private assignment-shaped text",
                    matched=assignment_match.group(0),
                )
            )
        url_match = UNSAFE_URL_PATTERN.search(value)
        if url_match:
            findings.append(
                ReviewPacketFinding(
                    path=_display_path(path),
                    reason="unsafe URL in packet content",
                    matched=url_match.group(0),
                )
            )


def _scan_key(
    key: str,
    value: Any,
    path: tuple[str, ...],
    findings: list[ReviewPacketFinding],
) -> None:
    for token in SECRET_KEY_TOKENS:
        if key == token or token in key:
            findings.append(
                ReviewPacketFinding(
                    path=_display_path((*path, key)),
                    reason="secret or private shaped packet key",
                    matched=token,
                )
            )
    if key in FORBIDDEN_KEYS:
        findings.append(
            ReviewPacketFinding(
                path=_display_path((*path, key)),
                reason="account, broker-routing, or order-affordance packet key",
                matched=key,
            )
        )
    if key in FALSE_ONLY_KEYS and value is not False:
        findings.append(
            ReviewPacketFinding(
                path=_display_path((*path, key)),
                reason="unsafe authorization boolean",
                matched=key,
            )
        )


def _validated_baseline(repo: Path, value: Any) -> dict[str, str]:
    baseline = _normalized_json_object(_required_mapping_value(value, "baseline"), "baseline")
    _expect_exact_keys(baseline, {"commit_sha", "subject", "tree_sha"}, "baseline")
    commit_sha = _validated_full_git_sha(baseline["commit_sha"], "baseline.commit_sha")
    tree_sha = _validated_full_git_sha(baseline["tree_sha"], "baseline.tree_sha")
    subject = _validated_text(baseline["subject"], "baseline.subject")
    resolved_commit = _git_text(repo, "rev-parse", f"{commit_sha}^{{commit}}")
    resolved_tree = _git_text(repo, "rev-parse", f"{commit_sha}^{{tree}}")
    resolved_subject = _git_text(repo, "show", "-s", "--format=%s", commit_sha)
    if resolved_commit != commit_sha:
        raise ReviewPacketError("baseline commit must resolve to the exact full commit identity")
    if resolved_tree != tree_sha:
        raise ReviewPacketError("baseline tree does not match the specification")
    if resolved_subject != subject:
        raise ReviewPacketError("baseline subject does not match the specification")
    return {"commit_sha": commit_sha, "tree_sha": tree_sha, "subject": subject}


def _build_source_manifest(
    repo: Path,
    commit_sha: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    raw_tree = _git_bytes(repo, "ls-tree", "-r", "-z", "--full-tree", commit_sha)
    tree_entries: list[tuple[str, str, str]] = []
    for raw_entry in raw_tree.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode, object_type, object_sha = metadata.decode("ascii").split(" ")
        if object_type != "blob":
            raise ReviewPacketError("baseline tree contains an unsupported non-blob entry")
        path = raw_path.decode("utf-8")
        _validated_relative_path(path, "source path")
        tree_entries.append((mode, object_sha, path))

    contents = _git_blob_batch(repo, [entry[1] for entry in tree_entries])
    entries: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for (mode, object_sha, path), content in zip(tree_entries, contents, strict=True):
        blobs[path] = content
        entries.append(
            {
                "bytes": len(content),
                "git_blob_sha": object_sha,
                "mode": mode,
                "path": path,
                "sha256": _sha256_bytes(content),
            }
        )
    entries.sort(key=lambda entry: entry["path"])
    return _digest_section({"entry_count": len(entries), "entries": entries}), blobs


def _git_blob_batch(repo: Path, object_shas: Sequence[str]) -> list[bytes]:
    request = "".join(f"{object_sha}\n" for object_sha in object_shas).encode("ascii")
    completed = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo,
        check=False,
        capture_output=True,
        input=request,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReviewPacketError(f"Git blob batch failed: {error or 'unknown error'}")

    output = completed.stdout
    cursor = 0
    contents: list[bytes] = []
    for expected_sha in object_shas:
        header_end = output.find(b"\n", cursor)
        if header_end < 0:
            raise ReviewPacketError("Git blob batch returned an incomplete header")
        header = output[cursor:header_end].decode("ascii").split(" ")
        if len(header) != 3 or header[0] != expected_sha or header[1] != "blob":
            raise ReviewPacketError("Git blob batch returned an unexpected object")
        try:
            size = int(header[2])
        except ValueError as exc:
            raise ReviewPacketError("Git blob batch returned an invalid size") from exc
        content_start = header_end + 1
        content_end = content_start + size
        if content_end >= len(output) or output[content_end : content_end + 1] != b"\n":
            raise ReviewPacketError("Git blob batch returned incomplete content")
        contents.append(output[content_start:content_end])
        cursor = content_end + 1
    if cursor != len(output):
        raise ReviewPacketError("Git blob batch returned unexpected trailing content")
    return contents


def _build_dependency_manifest(
    blobs: Mapping[str, bytes],
    source_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    source_by_path = _source_entries_by_path(source_manifest)
    missing = [path for path in DEPENDENCY_PATHS if path not in blobs]
    if missing:
        raise ReviewPacketError(f"baseline is missing dependency files: {', '.join(missing)}")
    dependency_files = [dict(source_by_path[path]) for path in DEPENDENCY_PATHS]
    packages = _python_dependency_inventory(blobs) + _npm_dependency_inventory(blobs)
    packages.sort(
        key=lambda package: (
            package["ecosystem"],
            package["name"],
            str(package["resolved_version"]),
        )
    )
    return _digest_section(
        {
            "file_count": len(dependency_files),
            "files": dependency_files,
            "npm_lock_status": "lockfile_present",
            "package_count": len(packages),
            "packages": packages,
            "python_lock_status": "unlocked_constraints",
        }
    )


def _python_dependency_inventory(blobs: Mapping[str, bytes]) -> list[dict[str, Any]]:
    project = tomllib.loads(blobs["backend/pyproject.toml"].decode("utf-8"))
    requirements = list(project["project"].get("dependencies", []))
    for group in project["project"].get("optional-dependencies", {}).values():
        requirements.extend(group)
    packages: list[dict[str, Any]] = []
    for requirement in requirements:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", requirement)
        if not match:
            raise ReviewPacketError("unsupported Python dependency declaration")
        packages.append(
            {
                "constraint": match.group(2) or "unconstrained",
                "ecosystem": "python",
                "name": match.group(1),
                "resolved_version": None,
            }
        )
    return packages


def _npm_dependency_inventory(blobs: Mapping[str, bytes]) -> list[dict[str, Any]]:
    package_json = _load_json_bytes(blobs["frontend/package.json"], "frontend package.json")
    package_lock = _load_json_bytes(blobs["frontend/package-lock.json"], "frontend package-lock")
    declared = {
        **package_json.get("dependencies", {}),
        **package_json.get("devDependencies", {}),
    }
    packages: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()
    for package_path, metadata in package_lock.get("packages", {}).items():
        if "node_modules/" not in package_path or not isinstance(metadata, Mapping):
            continue
        name = package_path.rsplit("node_modules/", 1)[1]
        version = str(metadata.get("version", "unknown"))
        identity = (name, version)
        if identity in observed:
            continue
        observed.add(identity)
        packages.append(
            {
                "constraint": str(declared.get(name, "transitive")),
                "ecosystem": "npm",
                "name": name,
                "resolved_version": version,
            }
        )
    return packages


def _build_test_manifest(
    blobs: Mapping[str, bytes],
    source_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    source_by_path = _source_entries_by_path(source_manifest)
    files: list[dict[str, Any]] = []
    for path, content in blobs.items():
        if not _is_test_path(path):
            continue
        text = content.decode("utf-8")
        definition_count = _test_definition_count(path, text)
        entry = dict(source_by_path[path])
        entry["definition_count"] = definition_count
        files.append(entry)
    files.sort(key=lambda entry: entry["path"])
    return _digest_section(
        {
            "definition_count": sum(entry["definition_count"] for entry in files),
            "file_count": len(files),
            "files": files,
        }
    )


def _build_evidence_manifest(
    raw_documents: Any,
    source_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    documents = _required_sequence(raw_documents, "evidence_documents")
    source_by_path = _source_entries_by_path(source_manifest)
    output: list[dict[str, Any]] = []
    observed: set[str] = set()
    for index, raw_document in enumerate(documents):
        document = _normalized_json_object(
            _required_mapping_value(raw_document, f"evidence_documents[{index}]"),
            "evidence document",
        )
        _expect_exact_keys(
            document,
            {"evidence_level", "path", "purpose", "review_status"},
            "evidence document",
        )
        path = _validated_relative_path(document["path"], "evidence document path")
        if path in observed:
            raise ReviewPacketError("evidence document paths must be unique")
        observed.add(path)
        if path not in source_by_path:
            raise ReviewPacketError(f"evidence document is not in the baseline: {path}")
        if document["review_status"] != "pending_independent_review":
            raise ReviewPacketError("evidence documents must remain pending independent review")
        if document["evidence_level"] not in {
            "automated_test",
            "documented",
            "source_inspected",
        }:
            raise ReviewPacketError("unsupported evidence document level")
        source_entry = source_by_path[path]
        output.append(
            {
                "bytes": source_entry["bytes"],
                "evidence_level": document["evidence_level"],
                "git_blob_sha": source_entry["git_blob_sha"],
                "path": path,
                "purpose": _validated_text(document["purpose"], "evidence document purpose"),
                "review_status": "pending_independent_review",
                "sha256": source_entry["sha256"],
            }
        )
    output.sort(key=lambda item: item["path"])
    return _digest_section({"document_count": len(output), "documents": output})


def _validated_verification(value: Any) -> dict[str, Any]:
    verification = _normalized_json_object(
        _required_mapping_value(value, "baseline_verification"),
        "baseline verification",
    )
    required = {
        "backend_tests",
        "checks",
        "commands",
        "evidence_level",
        "frontend_tests",
        "limitations",
        "resilience_tests",
        "result",
        "tree_was_clean",
    }
    _expect_exact_keys(verification, required, "baseline verification")
    if verification["evidence_level"] != "local_self_recorded":
        raise ReviewPacketError("baseline verification must remain local self-recorded evidence")
    if verification["result"] != "passed" or verification["tree_was_clean"] is not True:
        raise ReviewPacketError("baseline verification must record the observed clean-tree pass")
    _validated_string_list(verification["checks"], "verification checks")
    _validated_string_list(verification["commands"], "verification commands")
    _validated_string_list(verification["limitations"], "verification limitations")
    _validated_count_pair(verification["backend_tests"], "backend_tests", include_files=False)
    _validated_count_pair(verification["frontend_tests"], "frontend_tests", include_files=True)
    _validated_count_pair(verification["resilience_tests"], "resilience_tests", include_files=False)
    return verification


def _validated_review_scope(value: Any) -> list[dict[str, str]]:
    raw_scope = _required_sequence(value, "review_scope")
    scope: list[dict[str, str]] = []
    for index, raw_item in enumerate(raw_scope):
        item = _normalized_json_object(
            _required_mapping_value(raw_item, f"review_scope[{index}]"),
            "review scope item",
        )
        _expect_exact_keys(item, {"objective", "scope_id", "title"}, "review scope item")
        scope.append(
            {
                "objective": _validated_text(item["objective"], "review scope objective"),
                "scope_id": _validated_identifier(item["scope_id"], "review scope id"),
                "title": _validated_text(item["title"], "review scope title"),
            }
        )
    scope.sort(key=lambda item: item["scope_id"])
    if {item["scope_id"] for item in scope} != REQUIRED_SCOPE_IDS:
        raise ReviewPacketError("review scope must contain all eight approved areas exactly once")
    return scope


def _validated_traceability(
    value: Any,
    review_scope: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    controls = _required_sequence(value, "traceability")
    scope_ids = {item["scope_id"] for item in review_scope}
    output: list[dict[str, Any]] = []
    observed: set[str] = set()
    required = {
        "control_id",
        "evidence_level",
        "implementation_references",
        "requirement",
        "review_scope_id",
        "review_status",
        "test_references",
    }
    for index, raw_control in enumerate(controls):
        control = _normalized_json_object(
            _required_mapping_value(raw_control, f"traceability[{index}]"),
            "traceability control",
        )
        _expect_exact_keys(control, required, "traceability control")
        control_id = _validated_identifier(control["control_id"], "control_id")
        if control_id in observed:
            raise ReviewPacketError("traceability control IDs must be unique")
        observed.add(control_id)
        scope_id = _validated_identifier(control["review_scope_id"], "review_scope_id")
        if scope_id not in scope_ids:
            raise ReviewPacketError("traceability control references an unknown review scope")
        if control["review_status"] != "pending_independent_review":
            raise ReviewPacketError("traceability controls must remain pending independent review")
        output.append(
            {
                "control_id": control_id,
                "evidence_level": _validated_identifier(
                    control["evidence_level"], "traceability evidence_level"
                ),
                "implementation_references": list(
                    _validated_string_list(
                        control["implementation_references"],
                        "implementation_references",
                    )
                ),
                "requirement": _validated_text(control["requirement"], "control requirement"),
                "review_scope_id": scope_id,
                "review_status": "pending_independent_review",
                "test_references": list(
                    _validated_string_list(control["test_references"], "test_references")
                ),
            }
        )
    output.sort(key=lambda item: item["control_id"])
    return {"control_count": len(output), "controls": output}


def _validated_findings(value: Any) -> dict[str, Any]:
    raw_findings = _required_sequence(value, "findings")
    output: list[dict[str, Any]] = []
    observed: set[str] = set()
    required = {
        "blocking",
        "evidence_references",
        "finding_id",
        "owner_status",
        "resolution_state",
        "severity",
        "summary",
    }
    for index, raw_finding in enumerate(raw_findings):
        finding = _normalized_json_object(
            _required_mapping_value(raw_finding, f"findings[{index}]"),
            "pre-review finding",
        )
        _expect_exact_keys(finding, required, "pre-review finding")
        finding_id = _validated_identifier(finding["finding_id"], "finding_id")
        if finding_id in observed:
            raise ReviewPacketError("finding IDs must be unique")
        observed.add(finding_id)
        severity = finding["severity"]
        if severity not in {"P0", "P1", "P2", "P3"}:
            raise ReviewPacketError("finding severity must be P0, P1, P2, or P3")
        if finding["resolution_state"] != "open":
            raise ReviewPacketError("pre-review findings must remain open")
        if finding["owner_status"] not in {"unassigned", "internal_owner_needed"}:
            raise ReviewPacketError("pre-review finding owner status is unsupported")
        if not isinstance(finding["blocking"], bool):
            raise ReviewPacketError("finding blocking must be boolean")
        if severity in {"P0", "P1"} and finding["blocking"] is not True:
            raise ReviewPacketError("open P0/P1 findings must be blocking")
        output.append(
            {
                "blocking": finding["blocking"],
                "evidence_references": list(
                    _validated_string_list(
                        finding["evidence_references"],
                        "finding evidence_references",
                    )
                ),
                "finding_id": finding_id,
                "owner_status": finding["owner_status"],
                "resolution_state": "open",
                "severity": severity,
                "summary": _validated_text(finding["summary"], "finding summary"),
            }
        )
    output.sort(key=lambda item: item["finding_id"])
    return {"finding_count": len(output), "items": output}


def _validated_unresolved_evidence(value: Any) -> dict[str, Any]:
    raw_items = _required_sequence(value, "unresolved_evidence")
    output: list[dict[str, Any]] = []
    observed: set[str] = set()
    required = {"blocking_reason", "category", "evidence_references", "status"}
    for index, raw_item in enumerate(raw_items):
        item = _normalized_json_object(
            _required_mapping_value(raw_item, f"unresolved_evidence[{index}]"),
            "unresolved evidence item",
        )
        _expect_exact_keys(item, required, "unresolved evidence item")
        category = _validated_identifier(item["category"], "evidence category")
        if category in observed:
            raise ReviewPacketError("unresolved evidence categories must be unique")
        observed.add(category)
        status = item["status"]
        if status not in EVIDENCE_STATUSES or status == "verified":
            raise ReviewPacketError("Candidate Slice 061 cannot mark evidence verified")
        output.append(
            {
                "blocking_reason": _validated_text(
                    item["blocking_reason"], "evidence blocking_reason"
                ),
                "category": category,
                "evidence_references": list(
                    _validated_string_list(
                        item["evidence_references"],
                        "evidence_references",
                    )
                ),
                "status": status,
            }
        )
    output.sort(key=lambda item: item["category"])
    if {item["category"] for item in output} != REQUIRED_EVIDENCE_CATEGORIES:
        raise ReviewPacketError("all fourteen controlled-rollout evidence categories are required")
    external = next(item for item in output if item["category"] == "external_review")
    if external["status"] != "missing":
        raise ReviewPacketError("external-review evidence must remain missing")
    return {
        "blocking_count": len(output),
        "item_count": len(output),
        "items": output,
        "verified_count": 0,
    }


def _readiness_from_unresolved(unresolved: Mapping[str, Any]) -> dict[str, Any]:
    if unresolved["blocking_count"] != 14 or unresolved["verified_count"] != 0:
        raise ReviewPacketError("all fourteen unresolved evidence items must remain blocking")
    return {
        "blocking_evidence_count": 14,
        "decision": "no_go",
        "external_review_evidence": "missing",
        "result": "not_ready",
        "verified_evidence_count": 0,
    }


def _validate_specification(specification: Mapping[str, Any]) -> None:
    _expect_exact_keys(specification, REQUIRED_SPEC_KEYS, "packet specification")
    if specification["schema_version"] != 1:
        raise ReviewPacketError("packet specification schema_version must be 1")


def _validated_count_pair(value: Any, field_name: str, *, include_files: bool) -> None:
    counts = _required_mapping_value(value, field_name)
    required = {"passed", "files" if include_files else "collected"}
    _expect_exact_keys(counts, required, field_name)
    for key, count in counts.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ReviewPacketError(f"{field_name}.{key} must be a nonnegative integer")


def _source_entries_by_path(source_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(entry["path"]): dict(entry) for entry in source_manifest["entries"]}


def _is_test_path(path: str) -> bool:
    return (
        path.startswith("backend/tests/test_")
        and path.endswith(".py")
        or path.startswith("frontend/src/")
        and (path.endswith(".test.ts") or path.endswith(".test.tsx"))
    )


def _test_definition_count(path: str, text: str) -> int:
    if path.endswith(".py"):
        return len(re.findall(r"(?m)^def test_[A-Za-z0-9_]+\s*\(", text))
    return len(re.findall(r"\b(?:it|test)\s*\(", text))


def _digest_section(content: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalized_json_object(content, "packet section")
    normalized["content_sha256"] = _sha256_json(normalized)
    return normalized


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_repository_path(repo: Path, value: str | Path, field_name: str) -> Path:
    raw_path = Path(value)
    candidate = raw_path if raw_path.is_absolute() else repo / raw_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise ReviewPacketError(f"{field_name} must stay inside the repository") from exc
    if not resolved.is_file():
        raise ReviewPacketError(f"{field_name} must reference an existing file")
    return resolved


def _validated_relative_path(value: Any, field_name: str) -> str:
    text = _validated_text(value, field_name)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text or text.startswith("./"):
        raise ReviewPacketError(f"{field_name} must be a normalized repository-relative path")
    return text


def _validated_full_git_sha(value: Any, field_name: str) -> str:
    text = _validated_text(value, field_name)
    if FULL_GIT_SHA_PATTERN.fullmatch(text) is None:
        raise ReviewPacketError(f"{field_name} must be a full lowercase Git SHA")
    return text


def _validated_identifier(value: Any, field_name: str) -> str:
    text = _validated_text(value, field_name)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", text) is None:
        raise ReviewPacketError(f"{field_name} contains unsupported characters")
    return text


def _validated_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReviewPacketError(f"{field_name} must be a non-empty trimmed string")
    return value


def _validated_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    items = _required_sequence(value, field_name)
    output = tuple(_validated_text(item, field_name) for item in items)
    if not output:
        raise ReviewPacketError(f"{field_name} must not be empty")
    if len(set(output)) != len(output):
        raise ReviewPacketError(f"{field_name} must not contain duplicates")
    return output


def _expect_exact_keys(value: Mapping[str, Any], expected: set[str], field_name: str) -> None:
    if set(value) != expected:
        raise ReviewPacketError(f"{field_name} must contain exactly the approved fields")


def _required_mapping(value: Mapping[str, Any], key: str, field_name: str) -> Mapping[str, Any]:
    if key not in value:
        raise ReviewPacketError(f"{field_name}.{key} is required")
    return _required_mapping_value(value[key], f"{field_name}.{key}")


def _required_mapping_value(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewPacketError(f"{field_name} must be an object")
    return value


def _required_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, list) or not value:
        raise ReviewPacketError(f"{field_name} must be a non-empty array")
    return value


def _normalized_json_object(value: Any, field_name: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ReviewPacketError(f"{field_name} must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise ReviewPacketError(f"{field_name} must be a JSON object")
    return normalized


def _load_json_bytes(value: bytes, field_name: str) -> Any:
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewPacketError(f"{field_name} must be UTF-8 JSON") from exc


def _git_text(repo: Path, *arguments: str) -> str:
    return _git_bytes(repo, *arguments).decode("utf-8").strip()


def _git_bytes(repo: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReviewPacketError("local Git object inspection failed") from exc
    return result.stdout


def _normalized_key(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _display_path(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "packet"


def _finding_message(findings: tuple[ReviewPacketFinding, ...]) -> str:
    first = findings[0]
    return f"review packet safety scan failed at {first.path}: {first.reason}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or verify a local review packet")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--repository", required=True)
    generate.add_argument("--spec", required=True)
    generate.add_argument("--output", required=True)
    generate.add_argument("--digest-output", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--repository", required=True)
    verify.add_argument("--packet", required=True)
    verify.add_argument("--digest", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = _build_parser().parse_args(arguments)
    if parsed.command == "generate":
        packet = build_independent_review_packet(parsed.repository, parsed.spec)
        write_independent_review_packet(packet, parsed.output, parsed.digest_output)
        print(f"review packet generated: {packet.sha256()}")
        return 0
    result = verify_independent_review_packet(
        parsed.repository,
        parsed.packet,
        parsed.digest,
    )
    print(f"review packet verification: {result['result']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
