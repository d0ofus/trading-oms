from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.alerts import (
    AlertBook,
    AlertDispatchOutcome,
    AlertDispatchRequest,
    AlertIntent,
    AlertIntentRequest,
    NoopAlertDispatcher,
)
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.fake_broker import BrokerOrderTransition

POSITION_UPDATED_EVENT_TYPE = "position.updated"
VALID_PROTECTION_STATUSES = {"expected_protection_present", "missing_expected_protection"}


class PositionProtectionError(ValueError):
    """Raised when simulated position updates or protection checks are invalid."""


@dataclass(frozen=True)
class PositionUpdateRequest:
    update_id: str
    position_id: str
    fill_transition: BrokerOrderTransition
    expected_protection_present: bool
    expected_protection_kind: str
    monitored_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise PositionProtectionError("schema_version must be 1")
        _validated_identifier(self.update_id, "update_id")
        _validated_identifier(self.position_id, "position_id")
        if not isinstance(self.fill_transition, BrokerOrderTransition):
            raise PositionProtectionError("fill_transition must be a BrokerOrderTransition")
        if self.fill_transition.state != "filled":
            raise PositionProtectionError("fill_transition must be filled")
        if self.fill_transition.fill_price is None:
            raise PositionProtectionError("filled transitions require fill_price")
        if not isinstance(self.expected_protection_present, bool):
            raise PositionProtectionError("expected_protection_present must be a boolean")
        _validated_identifier(self.expected_protection_kind, "expected_protection_kind")
        _parse_timestamp(self.monitored_at, "monitored_at")
        _assert_json_serializable(self.to_payload(), "position update request")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "update_id": self.update_id,
            "position_id": self.position_id,
            "fill_transition": self.fill_transition.to_json_dict(),
            "expected_protection_present": self.expected_protection_present,
            "expected_protection_kind": self.expected_protection_kind,
            "monitored_at": self.monitored_at,
        }


@dataclass(frozen=True)
class SimulatedPosition:
    position_id: str
    symbol: str
    quantity: int
    average_price: float
    protection_status: str
    expected_protection_kind: str
    updated_at: str
    source_fill_reference: str
    journal_references: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise PositionProtectionError("schema_version must be 1")
        _validated_identifier(self.position_id, "position_id")
        _validated_symbol(self.symbol)
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise PositionProtectionError("quantity must be a positive integer")
        if isinstance(self.average_price, bool) or not isinstance(self.average_price, int | float):
            raise PositionProtectionError("average_price must be a positive number")
        if self.average_price <= 0:
            raise PositionProtectionError("average_price must be a positive number")
        if self.protection_status not in VALID_PROTECTION_STATUSES:
            raise PositionProtectionError("protection_status must be a known protection state")
        _validated_identifier(self.expected_protection_kind, "expected_protection_kind")
        _parse_timestamp(self.updated_at, "updated_at")
        _validated_identifier(self.source_fill_reference, "source_fill_reference")
        _validated_journal_references(self.journal_references)
        _assert_json_serializable(self.to_json_dict(), "simulated position")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "position_id": self.position_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "protection_status": self.protection_status,
            "expected_protection_kind": self.expected_protection_kind,
            "updated_at": self.updated_at,
            "source_fill_reference": self.source_fill_reference,
            "journal_references": list(self.journal_references),
        }


@dataclass(frozen=True)
class ProtectionMonitoringResult:
    position: SimulatedPosition
    alert_intent: AlertIntent | None
    alert_dispatch: AlertDispatchOutcome | None


class SimulatedPositionBook:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise PositionProtectionError("journal must be JsonlEventJournal")
        self._journal = journal
        self._alerts = AlertBook(journal)
        self._update_payloads: dict[str, dict[str, Any]] = {}
        self._update_results: dict[str, ProtectionMonitoringResult] = {}
        self._positions: dict[str, SimulatedPosition] = {}

    def record_fill(self, request: PositionUpdateRequest) -> ProtectionMonitoringResult:
        if not isinstance(request, PositionUpdateRequest):
            raise PositionProtectionError("request must be PositionUpdateRequest")

        request_payload = request.to_payload()
        existing_payload = self._update_payloads.get(request.update_id)
        if existing_payload is not None:
            if existing_payload != request_payload:
                raise PositionProtectionError("conflicting update_id")
            return self._update_results[request.update_id]

        position = self._position_from_fill(request)
        self._journal.append(
            event_type=POSITION_UPDATED_EVENT_TYPE,
            payload=position.to_json_dict(),
            timestamp=position.updated_at,
        )
        if position.protection_status == "missing_expected_protection":
            alert_intent, alert_dispatch = self._create_missing_protection_alert(position, request)
        else:
            alert_intent = None
            alert_dispatch = None

        result = ProtectionMonitoringResult(
            position=position,
            alert_intent=alert_intent,
            alert_dispatch=alert_dispatch,
        )
        self._positions[position.position_id] = position
        self._update_payloads[request.update_id] = request_payload
        self._update_results[request.update_id] = result
        return result

    def current_position(self, position_id: str) -> SimulatedPosition:
        _validated_identifier(position_id, "position_id")
        try:
            return self._positions[position_id]
        except KeyError as exc:
            raise PositionProtectionError("unknown position_id") from exc

    def _position_from_fill(self, request: PositionUpdateRequest) -> SimulatedPosition:
        fill = request.fill_transition
        quantity = fill.cumulative_filled_quantity
        if fill.side == "sell":
            quantity = -quantity
        return SimulatedPosition(
            position_id=request.position_id,
            symbol=fill.symbol,
            quantity=quantity,
            average_price=fill.fill_price or 0.0,
            protection_status=(
                "expected_protection_present"
                if request.expected_protection_present
                else "missing_expected_protection"
            ),
            expected_protection_kind=request.expected_protection_kind,
            updated_at=request.monitored_at,
            source_fill_reference=fill.fake_broker_order_id,
            journal_references=(_journal_reference(self._next_journal_sequence()),),
        )

    def _create_missing_protection_alert(
        self,
        position: SimulatedPosition,
        request: PositionUpdateRequest,
    ) -> tuple[AlertIntent, AlertDispatchOutcome]:
        alert = self._alerts.create_intent(
            AlertIntentRequest(
                alert_id=f"alert-{request.update_id}-missing-protection",
                source_event_type="position.protection_missing",
                source_event_reference=position.journal_references[-1],
                severity="critical",
                channel="local",
                created_at=request.monitored_at,
                title="Position protection missing",
                message="A risk-increasing simulated position is missing expected protection.",
                metadata={
                    "symbol": position.symbol,
                    "position_id": position.position_id,
                    "expected_protection": position.expected_protection_kind,
                },
            ),
        )
        dispatch = self._alerts.dispatch_alert(
            AlertDispatchRequest(
                dispatch_id=f"dispatch-{request.update_id}-missing-protection",
                alert_id=alert.alert_id,
                dispatched_at=request.monitored_at,
                reason="record_local_protection_alert",
            ),
            NoopAlertDispatcher(),
        )
        return alert, dispatch

    def _next_journal_sequence(self) -> int:
        records = self._journal.read_all()
        return records[-1].sequence + 1 if records else 1


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PositionProtectionError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise PositionProtectionError(f"{field_name} must not contain whitespace padding")
    return value


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol != symbol.upper():
        raise PositionProtectionError("symbol must be uppercase")
    return symbol


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _validated_identifier(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PositionProtectionError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PositionProtectionError(f"{field_name} must include a timezone")
    return parsed


def _validated_journal_references(references: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(references, tuple) or not references:
        raise PositionProtectionError("journal_references must be a non-empty tuple")
    for reference in references:
        _validated_identifier(reference, "journal_references")
        if not reference.startswith("journal_sequence:"):
            raise PositionProtectionError("journal_references must use journal_sequence references")
    return references


def _journal_reference(sequence: int) -> str:
    return f"journal_sequence:{sequence}"


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PositionProtectionError(f"{payload_name} must be JSON-serializable") from exc
