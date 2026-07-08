from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.read_models import OperationsReadModel
from trading_oms_backend.workflow_definitions import WorkflowDefinitionRecord
from trading_oms_backend.workflow_simulation_runs import WorkflowSimulationRunRecord


class AuditExportError(ValueError):
    """Raised when an audit export bundle would violate safety rules."""


SECRET_KEY_TOKENS = {
    "api_key",
    "apikey",
    "authorization",
    "certificate",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
}

FORBIDDEN_KEY_TOKENS = {
    "account_id",
    "broker_host",
    "connect_url",
    "place_order_url",
    "route_url",
    "submit_url",
    "transmit_url",
}

FALSE_ONLY_BOOLEAN_KEYS = {
    "arbitrary_code_allowed",
    "broker_transport_allowed",
    "live_trading_authorized",
    "live_trading_enabled",
}

FORBIDDEN_TEXT_TOKENS = {
    "account_id",
    "api_key",
    "authorization:",
    "bearer ",
    "broker_host",
    "eval(",
    "eval:",
    "ibkr connect",
    "javascript:",
    "password:",
    "password=",
    "place_order",
    "private_key",
    "route_order",
    "secret:",
    "secret=",
    "submit_order",
    "token:",
    "token=",
    "transmit_order",
}


@dataclass(frozen=True)
class AuditExportFinding:
    path: str
    reason: str
    matched: str

    def to_json_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "reason": self.reason,
            "matched": self.matched,
        }


@dataclass(frozen=True)
class AuditExportBundle:
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        _normalized_json_object(self.payload, "audit export bundle")
        findings = scan_for_unsafe_export_content(self.payload)
        if findings:
            raise AuditExportError(_findings_message(findings))

    def to_json_dict(self) -> dict[str, Any]:
        return _normalized_json_object(self.payload, "audit export bundle")

    def to_stable_json(self) -> str:
        return _stable_json(self.payload)


def build_audit_export_bundle(
    *,
    export_id: str,
    generated_at: str,
    review_reference: str,
    operations_read_model: OperationsReadModel | Mapping[str, Any],
    workflow_definitions: Iterable[WorkflowDefinitionRecord | Mapping[str, Any]],
    workflow_simulation_runs: Iterable[WorkflowSimulationRunRecord | Mapping[str, Any]],
    journal_records: Iterable[JournalRecord | Mapping[str, Any]],
) -> AuditExportBundle:
    _validated_identifier(export_id, "export_id")
    _parse_timestamp(generated_at, "generated_at")
    _validated_identifier(review_reference, "review_reference")
    operations_payload = _model_payload(operations_read_model, "operations_read_model")
    workflow_payloads = sorted(
        (_model_payload(record, "workflow_definition") for record in workflow_definitions),
        key=lambda payload: str(payload.get("workflow_id", "")),
    )
    run_payloads = sorted(
        (_model_payload(record, "workflow_simulation_run") for record in workflow_simulation_runs),
        key=lambda payload: (str(payload.get("workflow_id", "")), str(payload.get("run_id", ""))),
    )
    journal_payloads = sorted(
        (_journal_payload(record) for record in journal_records),
        key=lambda payload: int(payload.get("sequence", 0)),
    )
    workflow_ids = tuple(
        str(payload["workflow_id"]) for payload in workflow_payloads if "workflow_id" in payload
    )
    run_ids = tuple(str(payload["run_id"]) for payload in run_payloads if "run_id" in payload)
    journal_references = tuple(
        f"journal_sequence:{payload['sequence']}"
        for payload in journal_payloads
        if "sequence" in payload
    )
    payload = {
        "schema_version": 1,
        "bundle_type": "audit_review_bundle",
        "manifest": {
            "schema_version": 1,
            "export_id": export_id,
            "generated_at": generated_at,
            "review_reference": review_reference,
            "mode": "local_review_only",
            "external_delivery": "none",
            "live_trading_enabled": False,
            "live_trading_authorized": False,
            "workflow_ids": list(workflow_ids),
            "run_ids": list(run_ids),
            "journal_references": list(journal_references),
            "counts": {
                "workflow_definitions": len(workflow_payloads),
                "workflow_simulation_runs": len(run_payloads),
                "journal_records": len(journal_payloads),
                "audit_events": len(operations_payload.get("audit_events", [])),
            },
            "safety_scan": {
                "result": "passed",
                "finding_count": 0,
            },
        },
        "operations_read_model": operations_payload,
        "workflow_definitions": workflow_payloads,
        "workflow_simulation_runs": run_payloads,
        "journal_records": journal_payloads,
    }
    findings = scan_for_unsafe_export_content(payload)
    if findings:
        raise AuditExportError(_findings_message(findings))
    return AuditExportBundle(payload)


def write_audit_export_bundle(bundle: AuditExportBundle, path: str | Path) -> None:
    if not isinstance(bundle, AuditExportBundle):
        raise AuditExportError("bundle must be AuditExportBundle")
    export_path = Path(path)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(bundle.to_stable_json() + "\n", encoding="utf-8")


def scan_for_unsafe_export_content(value: Any) -> tuple[AuditExportFinding, ...]:
    findings: list[AuditExportFinding] = []
    _scan_value(value, (), findings)
    return tuple(findings)


def _scan_value(value: Any, path: tuple[str, ...], findings: list[AuditExportFinding]) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = _normalized_key(str(raw_key))
            _scan_key(key, path, nested, findings)
            _scan_value(nested, (*path, key), findings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_value(item, (*path, str(index)), findings)
    elif isinstance(value, str):
        normalized = value.lower().replace("-", "_")
        for token in FORBIDDEN_TEXT_TOKENS:
            if token in normalized:
                findings.append(
                    AuditExportFinding(
                        path=_path(path),
                        reason="forbidden export text",
                        matched=token,
                    )
                )


def _scan_key(
    key: str,
    path: tuple[str, ...],
    value: Any,
    findings: list[AuditExportFinding],
) -> None:
    for token in SECRET_KEY_TOKENS:
        if key == token or token in key:
            findings.append(
                AuditExportFinding(
                    path=_path((*path, key)),
                    reason="secret-shaped export key",
                    matched=token,
                )
            )
    if key in FORBIDDEN_KEY_TOKENS:
        findings.append(
            AuditExportFinding(
                path=_path((*path, key)),
                reason="broker/live routing export key",
                matched=key,
            )
        )
    if key in {"live_mode", "route_live", "submit_live", "transmit_live"}:
        findings.append(
            AuditExportFinding(
                path=_path((*path, key)),
                reason="live-control export key",
                matched=key,
            )
        )
    if key in FALSE_ONLY_BOOLEAN_KEYS and value is not False:
        findings.append(
            AuditExportFinding(
                path=_path((*path, key)),
                reason="unsafe boolean export value",
                matched=key,
            )
        )


def _model_payload(value: Any, payload_name: str) -> dict[str, Any]:
    if isinstance(value, OperationsReadModel):
        return _normalized_json_object(value.to_json_dict(), payload_name)
    if isinstance(value, WorkflowDefinitionRecord):
        return _normalized_json_object(value.to_json_dict(), payload_name)
    if isinstance(value, WorkflowSimulationRunRecord):
        return _normalized_json_object(value.to_json_dict(), payload_name)
    if isinstance(value, Mapping):
        return _normalized_json_object(value, payload_name)
    raise AuditExportError(f"{payload_name} must be a supported audit export record")


def _journal_payload(value: JournalRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, JournalRecord):
        return _normalized_json_object(value.to_json_dict(), "journal_record")
    if isinstance(value, Mapping):
        return _normalized_json_object(value, "journal_record")
    raise AuditExportError("journal_record must be JournalRecord or mapping")


def _normalized_json_object(value: Mapping[str, Any], payload_name: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AuditExportError(f"{payload_name} must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise AuditExportError(f"{payload_name} must be a JSON object")
    return normalized


def _stable_json(value: Mapping[str, Any]) -> str:
    normalized = _normalized_json_object(value, "audit export bundle")
    return json.dumps(normalized, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditExportError(f"{field_name} must be a non-empty string")
    if value.strip() != value:
        raise AuditExportError(f"{field_name} must not contain leading or trailing whitespace")
    findings = scan_for_unsafe_export_content({field_name: value})
    if findings:
        raise AuditExportError(_findings_message(findings))
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _validated_identifier(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditExportError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuditExportError(f"{field_name} must include a timezone")
    return parsed


def _findings_message(findings: tuple[AuditExportFinding, ...]) -> str:
    first = findings[0]
    return f"audit export safety scan failed at {first.path}: {first.reason}"


def _normalized_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _path(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "payload"
