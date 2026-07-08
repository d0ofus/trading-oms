from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from trading_oms_backend.event_journal import JsonlEventJournal

LIVE_TRADING_READINESS_EVENT_TYPE = "live_readiness.evaluated"

READINESS_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("paper_trading_history_reviewed", "Paper trading history reviewed."),
    ("risk_engine_complete", "Risk engine complete."),
    ("oms_state_machine_complete", "OMS state machine complete."),
    ("event_journal_complete", "Event journal complete."),
    ("approval_flow_complete", "Approval flow complete."),
    ("reconnect_reconciliation_tested", "Reconnect/reconciliation tested."),
    ("chaos_tests_passing", "Chaos tests passing."),
    ("duplicate_order_prevention_tested", "Duplicate order prevention tested."),
    ("stale_data_blocking_tested", "Stale data blocking tested."),
    ("emergency_stop_implemented", "Emergency stop implemented."),
    ("secrets_management_reviewed", "Secrets management reviewed."),
    ("network_exposure_reviewed", "Network exposure reviewed."),
    ("external_code_review_completed", "External code review completed."),
    ("explicit_human_approval_recorded", "Explicit human approval recorded."),
)

ReadinessResult = Literal["not_ready", "ready_for_final_review"]
ReadinessCheckStatus = Literal["passed", "failed"]


class LiveTradingReadinessError(ValueError):
    """Raised when live-readiness inputs violate the safety gate."""


@dataclass(frozen=True)
class LiveTradingReadinessEvidence:
    paper_trading_history_reviewed: bool = False
    risk_engine_complete: bool = False
    oms_state_machine_complete: bool = False
    event_journal_complete: bool = False
    approval_flow_complete: bool = False
    reconnect_reconciliation_tested: bool = False
    chaos_tests_passing: bool = False
    duplicate_order_prevention_tested: bool = False
    stale_data_blocking_tested: bool = False
    emergency_stop_implemented: bool = False
    secrets_management_reviewed: bool = False
    network_exposure_reviewed: bool = False
    external_code_review_completed: bool = False
    explicit_human_approval_recorded: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise LiveTradingReadinessError("schema_version must be 1")
        for requirement_name, _description in READINESS_REQUIREMENTS:
            if not isinstance(getattr(self, requirement_name), bool):
                raise LiveTradingReadinessError(f"{requirement_name} must be a boolean")
        _assert_json_serializable(self.to_json_dict(), "live readiness evidence")

    def value_for(self, requirement_name: str) -> bool:
        if requirement_name not in {name for name, _description in READINESS_REQUIREMENTS}:
            raise LiveTradingReadinessError("unknown readiness requirement")
        return getattr(self, requirement_name)

    def to_json_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"schema_version": self.schema_version}
        for requirement_name, _description in READINESS_REQUIREMENTS:
            payload[requirement_name] = getattr(self, requirement_name)
        return payload


@dataclass(frozen=True)
class ReadinessCheckResult:
    name: str
    description: str
    status: ReadinessCheckStatus
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise LiveTradingReadinessError("schema_version must be 1")
        _validated_identifier(self.name, "name")
        _validated_description(self.description, "description")
        if self.status not in {"passed", "failed"}:
            raise LiveTradingReadinessError("status must be passed or failed")
        if self.reason not in {"evidence_recorded", "missing_evidence"}:
            raise LiveTradingReadinessError("reason must be evidence_recorded or missing_evidence")
        _assert_json_serializable(self.to_json_dict(), "readiness check result")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LiveTradingReadinessDecision:
    evaluation_id: str
    evaluated_at: str
    result: ReadinessResult
    checks: tuple[ReadinessCheckResult, ...]
    required_human_action: str
    live_trading_enabled: bool = False
    live_trading_authorized: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def failed_checks(self) -> list[ReadinessCheckResult]:
        return [check for check in self.checks if check.status == "failed"]

    def failed_check_names(self) -> list[str]:
        return [check.name for check in self.failed_checks()]

    def check_by_name(self, name: str) -> ReadinessCheckResult:
        for check in self.checks:
            if check.name == name:
                return check
        raise LiveTradingReadinessError(f"readiness check does not exist: {name}")

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise LiveTradingReadinessError("schema_version must be 1")
        _validated_identifier(self.evaluation_id, "evaluation_id")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if self.result not in {"not_ready", "ready_for_final_review"}:
            raise LiveTradingReadinessError("result must be not_ready or ready_for_final_review")
        if not isinstance(self.checks, tuple) or len(self.checks) != len(READINESS_REQUIREMENTS):
            raise LiveTradingReadinessError("checks must cover every readiness requirement")
        expected_names = tuple(name for name, _description in READINESS_REQUIREMENTS)
        if tuple(check.name for check in self.checks) != expected_names:
            raise LiveTradingReadinessError("checks must be in readiness requirement order")
        for check in self.checks:
            if not isinstance(check, ReadinessCheckResult):
                raise LiveTradingReadinessError("checks must contain ReadinessCheckResult values")
        failed_checks = self.failed_checks()
        if self.result == "ready_for_final_review" and failed_checks:
            raise LiveTradingReadinessError("ready_for_final_review must not contain failed checks")
        if self.result == "not_ready" and not failed_checks:
            raise LiveTradingReadinessError("not_ready decisions must contain failed checks")
        if self.live_trading_enabled is not False:
            raise LiveTradingReadinessError("live_trading_enabled must remain false")
        if self.live_trading_authorized is not False:
            raise LiveTradingReadinessError("live_trading_authorized must remain false")
        _validated_identifier(self.required_human_action, "required_human_action")
        _assert_json_serializable(self.to_json_dict(), "live readiness decision")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_id": self.evaluation_id,
            "evaluated_at": self.evaluated_at,
            "result": self.result,
            "required_human_action": self.required_human_action,
            "live_trading_enabled": self.live_trading_enabled,
            "live_trading_authorized": self.live_trading_authorized,
            "checks": [check.to_json_dict() for check in self.checks],
            "failed_checks": self.failed_check_names(),
        }


def evaluate_live_trading_readiness(
    *,
    evidence: LiveTradingReadinessEvidence,
    journal: JsonlEventJournal,
    evaluation_id: str,
    evaluated_at: str,
    requested_live_trading_enabled: bool = False,
) -> LiveTradingReadinessDecision:
    if not isinstance(evidence, LiveTradingReadinessEvidence):
        raise LiveTradingReadinessError("evidence must be LiveTradingReadinessEvidence")
    if not isinstance(journal, JsonlEventJournal):
        raise LiveTradingReadinessError("journal must be a JsonlEventJournal")
    if not isinstance(requested_live_trading_enabled, bool):
        raise LiveTradingReadinessError("requested_live_trading_enabled must be a boolean")
    if requested_live_trading_enabled:
        raise LiveTradingReadinessError("readiness evaluation cannot enable live trading")

    _validated_identifier(evaluation_id, "evaluation_id")
    _parse_timestamp(evaluated_at, "evaluated_at")

    checks = tuple(
        _check_requirement(evidence, requirement_name, description)
        for requirement_name, description in READINESS_REQUIREMENTS
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    result: ReadinessResult = "not_ready" if failed_checks else "ready_for_final_review"
    required_human_action = (
        "collect_missing_evidence"
        if failed_checks
        else "external_review_and_explicit_rollout_approval"
    )
    decision = LiveTradingReadinessDecision(
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
        result=result,
        checks=checks,
        required_human_action=required_human_action,
        live_trading_enabled=False,
        live_trading_authorized=False,
    )
    journal.append(
        event_type=LIVE_TRADING_READINESS_EVENT_TYPE,
        payload=decision.to_json_dict(),
        timestamp=decision.evaluated_at,
    )
    return decision


def _check_requirement(
    evidence: LiveTradingReadinessEvidence,
    requirement_name: str,
    description: str,
) -> ReadinessCheckResult:
    if evidence.value_for(requirement_name):
        return ReadinessCheckResult(
            name=requirement_name,
            description=description,
            status="passed",
            reason="evidence_recorded",
        )
    return ReadinessCheckResult(
        name=requirement_name,
        description=description,
        status="failed",
        reason="missing_evidence",
    )


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveTradingReadinessError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise LiveTradingReadinessError(
            f"{field_name} must not contain leading or trailing whitespace"
        )
    _reject_forbidden_text(value, field_name)
    return value


def _validated_description(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveTradingReadinessError(f"{field_name} must be a non-empty string")
    _reject_forbidden_text(value, field_name)
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise LiveTradingReadinessError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LiveTradingReadinessError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveTradingReadinessError(f"{field_name} must include a timezone")
    return parsed


def _reject_forbidden_text(value: str, field_name: str) -> None:
    normalized = value.lower()
    forbidden_markers = (
        "account=",
        "account:",
        "api_key=",
        "api_key:",
        "authorization=",
        "authorization:",
        "password=",
        "password:",
        "private_key=",
        "private_key:",
        "secret=",
        "secret:",
        "token=",
        "token:",
    )
    if any(marker in normalized for marker in forbidden_markers):
        raise LiveTradingReadinessError(f"{field_name} contains credential-shaped text")


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LiveTradingReadinessError(f"{payload_name} must be JSON-serializable") from exc
