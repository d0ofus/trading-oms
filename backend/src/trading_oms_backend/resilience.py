from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.risk_engine import (
    RiskDecision,
    RiskEvaluationRequest,
    RiskPolicy,
    evaluate_risk,
)

RESILIENCE_DISCONNECT_EVENT_TYPE = "resilience.connection.disconnected"
RESILIENCE_RECONNECT_EVENT_TYPE = "resilience.connection.reconnected"
RESILIENCE_UNKNOWN_BROKER_STATE_EVENT_TYPE = "resilience.broker_state.unknown"
RESILIENCE_RECONCILIATION_STARTED_EVENT_TYPE = "resilience.reconciliation.started"
RESILIENCE_RECONCILIATION_COMPLETED_EVENT_TYPE = "resilience.reconciliation.completed"
RESILIENCE_CHAOS_SCENARIO_EVENT_TYPE = "resilience.chaos.scenario.completed"

VALID_RESILIENCE_EVENT_TYPES = {
    RESILIENCE_DISCONNECT_EVENT_TYPE,
    RESILIENCE_RECONNECT_EVENT_TYPE,
    RESILIENCE_UNKNOWN_BROKER_STATE_EVENT_TYPE,
    RESILIENCE_RECONCILIATION_STARTED_EVENT_TYPE,
    RESILIENCE_RECONCILIATION_COMPLETED_EVENT_TYPE,
}

ResilienceEventType = Literal[
    "resilience.connection.disconnected",
    "resilience.connection.reconnected",
    "resilience.broker_state.unknown",
    "resilience.reconciliation.started",
    "resilience.reconciliation.completed",
]

_CHAOS_DISCONNECTED_AT = "2026-07-06T00:03:00Z"
_CHAOS_RECONNECTED_AT = "2026-07-06T00:03:10Z"
_CHAOS_UNKNOWN_STATE_AT = "2026-07-06T00:03:15Z"
_CHAOS_RECONCILIATION_STARTED_AT = "2026-07-06T00:03:20Z"
_CHAOS_RECONCILIATION_COMPLETED_AT = "2026-07-06T00:03:30Z"

_DEFAULT_COMPONENT = "resilience_monitor"
_FORBIDDEN_TEXT_MARKERS = (
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


class ResilienceError(ValueError):
    """Raised when resilience events or scenarios violate safety rules."""


@dataclass(frozen=True)
class ReconciliationSnapshot:
    snapshot_id: str
    captured_at: str
    broker_state_known: bool
    open_order_ids: tuple[str, ...]
    position_symbols: tuple[str, ...]
    requires_operator_review: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @property
    def reconciled_without_review(self) -> bool:
        return self.broker_state_known and not self.requires_operator_review

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ResilienceError("schema_version must be 1")
        _validated_identifier(self.snapshot_id, "snapshot_id")
        _parse_timestamp(self.captured_at, "captured_at")
        if not isinstance(self.broker_state_known, bool):
            raise ResilienceError("broker_state_known must be a boolean")
        if not isinstance(self.open_order_ids, tuple):
            raise ResilienceError("open_order_ids must be a tuple")
        if len(set(self.open_order_ids)) != len(self.open_order_ids):
            raise ResilienceError("open_order_ids must not contain duplicates")
        for open_order_id in self.open_order_ids:
            _validated_identifier(open_order_id, "open_order_ids")
        if not isinstance(self.position_symbols, tuple):
            raise ResilienceError("position_symbols must be a tuple")
        if len(set(self.position_symbols)) != len(self.position_symbols):
            raise ResilienceError("position_symbols must not contain duplicates")
        for symbol in self.position_symbols:
            _validated_symbol(symbol, "position_symbols")
        if not isinstance(self.requires_operator_review, bool):
            raise ResilienceError("requires_operator_review must be a boolean")
        _assert_json_serializable(self.to_json_dict(), "reconciliation snapshot")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "captured_at": self.captured_at,
            "broker_state_known": self.broker_state_known,
            "open_order_ids": list(self.open_order_ids),
            "position_symbols": list(self.position_symbols),
            "requires_operator_review": self.requires_operator_review,
            "reconciled_without_review": self.reconciled_without_review,
        }


@dataclass(frozen=True)
class ResilienceEvent:
    event_id: str
    event_type: ResilienceEventType
    occurred_at: str
    component: str
    reason: str
    requires_reconciliation: bool
    blocks_risk_increasing: bool
    details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    @classmethod
    def from_json_dict(cls, raw_event: Mapping[str, Any]) -> ResilienceEvent:
        if not isinstance(raw_event, Mapping):
            raise ResilienceError("resilience event must be a JSON object")

        try:
            event_id = raw_event["event_id"]
            event_type = raw_event["event_type"]
            occurred_at = raw_event["occurred_at"]
            component = raw_event["component"]
            reason = raw_event["reason"]
            requires_reconciliation = raw_event["requires_reconciliation"]
            blocks_risk_increasing = raw_event["blocks_risk_increasing"]
        except KeyError as exc:
            raise ResilienceError(f"resilience event is missing {exc.args[0]}") from exc

        raw_details = raw_event.get("details", {})
        if not isinstance(raw_details, Mapping):
            raise ResilienceError("details must be a JSON object")

        return cls(
            schema_version=raw_event.get("schema_version", 1),
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=requires_reconciliation,
            blocks_risk_increasing=blocks_risk_increasing,
            details=dict(raw_details),
        )

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ResilienceError("schema_version must be 1")
        _validated_identifier(self.event_id, "event_id")
        if self.event_type not in VALID_RESILIENCE_EVENT_TYPES:
            raise ResilienceError("event_type must be a known resilience event type")
        _parse_timestamp(self.occurred_at, "occurred_at")
        _validated_identifier(self.component, "component")
        _validated_identifier(self.reason, "reason")
        if not isinstance(self.requires_reconciliation, bool):
            raise ResilienceError("requires_reconciliation must be a boolean")
        if not isinstance(self.blocks_risk_increasing, bool):
            raise ResilienceError("blocks_risk_increasing must be a boolean")
        if not isinstance(self.details, dict):
            raise ResilienceError("details must be a JSON object")
        _assert_json_serializable(self.to_json_dict(), "resilience event")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "component": self.component,
            "reason": self.reason,
            "requires_reconciliation": self.requires_reconciliation,
            "blocks_risk_increasing": self.blocks_risk_increasing,
            "details": self.details,
        }


@dataclass(frozen=True)
class ReconnectReconciliationChaosResult:
    scenario_id: str
    completed_at: str
    events: tuple[ResilienceEvent, ...]
    stale_market_data_decision: RiskDecision
    unknown_state_decision: RiskDecision
    requires_reconciliation: bool
    blocks_risk_increasing: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ResilienceError("schema_version must be 1")
        _validated_identifier(self.scenario_id, "scenario_id")
        _parse_timestamp(self.completed_at, "completed_at")
        if not isinstance(self.events, tuple) or not self.events:
            raise ResilienceError("events must be a non-empty tuple")
        for event in self.events:
            if not isinstance(event, ResilienceEvent):
                raise ResilienceError("events must contain ResilienceEvent values")
        if not isinstance(self.stale_market_data_decision, RiskDecision):
            raise ResilienceError("stale_market_data_decision must be a RiskDecision")
        if not isinstance(self.unknown_state_decision, RiskDecision):
            raise ResilienceError("unknown_state_decision must be a RiskDecision")
        if not isinstance(self.requires_reconciliation, bool):
            raise ResilienceError("requires_reconciliation must be a boolean")
        if not isinstance(self.blocks_risk_increasing, bool):
            raise ResilienceError("blocks_risk_increasing must be a boolean")
        _assert_json_serializable(self.to_json_dict(), "chaos scenario result")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "completed_at": self.completed_at,
            "events": [event.to_json_dict() for event in self.events],
            "stale_market_data_decision": _risk_decision_summary(self.stale_market_data_decision),
            "unknown_state_decision": _risk_decision_summary(self.unknown_state_decision),
            "requires_reconciliation": self.requires_reconciliation,
            "blocks_risk_increasing": self.blocks_risk_increasing,
        }


class ResilienceMonitor:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise ResilienceError("journal must be a JsonlEventJournal")
        self._journal = journal
        self._events_by_id: dict[str, ResilienceEvent] = {}
        self._requires_reconciliation = False
        self._blocks_risk_increasing = False
        self._load_existing_resilience_events()

    @property
    def requires_reconciliation(self) -> bool:
        return self._requires_reconciliation

    @property
    def blocks_risk_increasing(self) -> bool:
        return self._blocks_risk_increasing

    def record_disconnect(
        self,
        *,
        event_id: str,
        occurred_at: str,
        reason: str,
        component: str = _DEFAULT_COMPONENT,
    ) -> ResilienceEvent:
        return self._record_event(
            event_id=event_id,
            event_type=RESILIENCE_DISCONNECT_EVENT_TYPE,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=True,
            blocks_risk_increasing=True,
        )

    def record_reconnect(
        self,
        *,
        event_id: str,
        occurred_at: str,
        reason: str,
        component: str = _DEFAULT_COMPONENT,
    ) -> ResilienceEvent:
        return self._record_event(
            event_id=event_id,
            event_type=RESILIENCE_RECONNECT_EVENT_TYPE,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=True,
            blocks_risk_increasing=True,
        )

    def record_unknown_broker_state(
        self,
        *,
        event_id: str,
        occurred_at: str,
        reason: str,
        component: str = _DEFAULT_COMPONENT,
    ) -> ResilienceEvent:
        return self._record_event(
            event_id=event_id,
            event_type=RESILIENCE_UNKNOWN_BROKER_STATE_EVENT_TYPE,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=True,
            blocks_risk_increasing=True,
        )

    def start_reconciliation(
        self,
        *,
        event_id: str,
        occurred_at: str,
        reason: str,
        snapshot: ReconciliationSnapshot,
        component: str = _DEFAULT_COMPONENT,
    ) -> ResilienceEvent:
        _validated_snapshot(snapshot)
        return self._record_event(
            event_id=event_id,
            event_type=RESILIENCE_RECONCILIATION_STARTED_EVENT_TYPE,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=True,
            blocks_risk_increasing=True,
            details={"snapshot": snapshot.to_json_dict()},
        )

    def complete_reconciliation(
        self,
        *,
        event_id: str,
        occurred_at: str,
        reason: str,
        snapshot: ReconciliationSnapshot,
        component: str = _DEFAULT_COMPONENT,
    ) -> ResilienceEvent:
        _validated_snapshot(snapshot)
        still_requires_reconciliation = not snapshot.reconciled_without_review
        return self._record_event(
            event_id=event_id,
            event_type=RESILIENCE_RECONCILIATION_COMPLETED_EVENT_TYPE,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=still_requires_reconciliation,
            blocks_risk_increasing=still_requires_reconciliation,
            details={"snapshot": snapshot.to_json_dict()},
        )

    def _record_event(
        self,
        *,
        event_id: str,
        event_type: ResilienceEventType,
        occurred_at: str,
        component: str,
        reason: str,
        requires_reconciliation: bool,
        blocks_risk_increasing: bool,
        details: dict[str, Any] | None = None,
    ) -> ResilienceEvent:
        event = ResilienceEvent(
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            component=component,
            reason=reason,
            requires_reconciliation=requires_reconciliation,
            blocks_risk_increasing=blocks_risk_increasing,
            details={} if details is None else details,
        )

        existing_event = self._events_by_id.get(event.event_id)
        if existing_event is not None:
            if existing_event.to_json_dict() != event.to_json_dict():
                raise ResilienceError("conflicting duplicate resilience event_id")
            return existing_event

        self._journal.append(
            event_type=event.event_type,
            payload=event.to_json_dict(),
            timestamp=event.occurred_at,
        )
        self._events_by_id[event.event_id] = event
        self._apply_event_state(event)
        return event

    def _load_existing_resilience_events(self) -> None:
        for record in self._journal.read_all():
            if record.event_type not in VALID_RESILIENCE_EVENT_TYPES:
                continue
            event = ResilienceEvent.from_json_dict(record.payload)
            if event.event_type != record.event_type:
                raise ResilienceError("journal record type must match resilience event payload")
            existing_event = self._events_by_id.get(event.event_id)
            if existing_event is not None and existing_event.to_json_dict() != event.to_json_dict():
                raise ResilienceError("journal contains conflicting duplicate resilience event_id")
            self._events_by_id[event.event_id] = event
            self._apply_event_state(event)

    def _apply_event_state(self, event: ResilienceEvent) -> None:
        self._requires_reconciliation = event.requires_reconciliation
        self._blocks_risk_increasing = event.blocks_risk_increasing


def run_reconnect_reconciliation_chaos_scenario(
    *,
    journal: JsonlEventJournal,
    scenario_id: str,
    policy: RiskPolicy,
    stale_market_data_request: RiskEvaluationRequest,
    unknown_state_request: RiskEvaluationRequest,
) -> ReconnectReconciliationChaosResult:
    if not isinstance(journal, JsonlEventJournal):
        raise ResilienceError("journal must be a JsonlEventJournal")
    _validated_identifier(scenario_id, "scenario_id")
    if not isinstance(policy, RiskPolicy):
        raise ResilienceError("policy must be a RiskPolicy")
    if not isinstance(stale_market_data_request, RiskEvaluationRequest):
        raise ResilienceError("stale_market_data_request must be a RiskEvaluationRequest")
    if not isinstance(unknown_state_request, RiskEvaluationRequest):
        raise ResilienceError("unknown_state_request must be a RiskEvaluationRequest")

    monitor = ResilienceMonitor(journal)
    disconnected = monitor.record_disconnect(
        event_id=f"{scenario_id}-disconnect",
        occurred_at=_CHAOS_DISCONNECTED_AT,
        reason="local_paper_session_disconnected",
    )
    reconnected = monitor.record_reconnect(
        event_id=f"{scenario_id}-reconnect",
        occurred_at=_CHAOS_RECONNECTED_AT,
        reason="local_paper_session_reconnected",
    )
    unknown_state = monitor.record_unknown_broker_state(
        event_id=f"{scenario_id}-unknown-state",
        occurred_at=_CHAOS_UNKNOWN_STATE_AT,
        reason="broker_state_unknown_after_reconnect",
    )
    reconciliation_started = monitor.start_reconciliation(
        event_id=f"{scenario_id}-reconciliation-started",
        occurred_at=_CHAOS_RECONCILIATION_STARTED_AT,
        reason="post_reconnect_reconciliation_required",
        snapshot=ReconciliationSnapshot(
            snapshot_id=f"{scenario_id}-snapshot-started",
            captured_at=_CHAOS_RECONCILIATION_STARTED_AT,
            broker_state_known=False,
            open_order_ids=(),
            position_symbols=(),
            requires_operator_review=True,
        ),
    )

    stale_market_data_decision = evaluate_risk(stale_market_data_request, policy, journal)
    unknown_state_decision = evaluate_risk(unknown_state_request, policy, journal)
    _assert_expected_chaos_decision(
        stale_market_data_decision,
        check_name="market_data_freshness",
        reason="market_data_stale",
    )
    _assert_expected_chaos_decision(
        unknown_state_decision,
        check_name="broker_state_known",
        reason="unknown_broker_state_blocks_risk_increase",
    )

    reconciliation_completed = monitor.complete_reconciliation(
        event_id=f"{scenario_id}-reconciliation-completed",
        occurred_at=_CHAOS_RECONCILIATION_COMPLETED_AT,
        reason="local_state_matches_known_paper_snapshot",
        snapshot=ReconciliationSnapshot(
            snapshot_id=f"{scenario_id}-snapshot-completed",
            captured_at=_CHAOS_RECONCILIATION_COMPLETED_AT,
            broker_state_known=True,
            open_order_ids=(),
            position_symbols=("AAPL",),
            requires_operator_review=False,
        ),
    )
    result = ReconnectReconciliationChaosResult(
        scenario_id=scenario_id,
        completed_at=_CHAOS_RECONCILIATION_COMPLETED_AT,
        events=(
            disconnected,
            reconnected,
            unknown_state,
            reconciliation_started,
            reconciliation_completed,
        ),
        stale_market_data_decision=stale_market_data_decision,
        unknown_state_decision=unknown_state_decision,
        requires_reconciliation=monitor.requires_reconciliation,
        blocks_risk_increasing=monitor.blocks_risk_increasing,
    )
    journal.append(
        event_type=RESILIENCE_CHAOS_SCENARIO_EVENT_TYPE,
        payload=result.to_json_dict(),
        timestamp=result.completed_at,
    )
    return result


def _assert_expected_chaos_decision(
    decision: RiskDecision,
    *,
    check_name: str,
    reason: str,
) -> None:
    if decision.result != "blocked":
        raise ResilienceError(f"chaos risk decision must be blocked for {check_name}")
    if decision.check_by_name(check_name).reason != reason:
        raise ResilienceError(f"chaos risk decision did not fail {check_name} as expected")


def _risk_decision_summary(decision: RiskDecision) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": decision.request_id,
        "evaluated_at": decision.evaluated_at,
        "symbol": decision.symbol,
        "risk_intent": decision.risk_intent,
        "result": decision.result,
        "failed_checks": [
            {
                "name": check.name,
                "reason": check.reason,
            }
            for check in decision.failed_checks()
        ],
    }


def _validated_snapshot(snapshot: ReconciliationSnapshot) -> None:
    if not isinstance(snapshot, ReconciliationSnapshot):
        raise ResilienceError("snapshot must be a ReconciliationSnapshot")


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResilienceError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ResilienceError(f"{field_name} must not contain leading or trailing whitespace")
    _reject_forbidden_text(value, field_name)
    return value


def _validated_symbol(symbol: str, field_name: str) -> str:
    _validated_identifier(symbol, field_name)
    if symbol != symbol.upper():
        raise ResilienceError(f"{field_name} must be uppercase")
    return symbol


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ResilienceError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResilienceError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResilienceError(f"{field_name} must include a timezone")
    return parsed


def _reject_forbidden_text(value: str, field_name: str) -> None:
    normalized = value.lower()
    if any(marker in normalized for marker in _FORBIDDEN_TEXT_MARKERS):
        raise ResilienceError(f"{field_name} contains credential-shaped text")


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResilienceError(f"{payload_name} must be JSON-serializable") from exc
