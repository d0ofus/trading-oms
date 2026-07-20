from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.event_journal import JsonlEventJournal

APPROVAL_TICKET_CREATED_EVENT_TYPE = "approval.ticket.created"
APPROVAL_DECISION_EVENT_TYPE = "approval.ticket.decided"

VALID_DECISIONS = {"approved", "rejected", "expired", "cancelled"}
VALID_RISK_INTENTS = {"increase", "reduce"}
VALID_SIDES = {"buy", "sell"}
VALID_TICKET_STATUSES = {"pending", "approved", "rejected", "expired", "cancelled"}


class ApprovalTicketError(ValueError):
    """Raised when approval ticket inputs, decisions, or state changes are invalid."""


@dataclass(frozen=True)
class ApprovalTicketCreateRequest:
    ticket_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    risk_intent: str
    risk_decision_id: str
    risk_decision_result: str
    oms_transition_reference: str
    oms_state: str
    created_at: str
    expires_at: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ApprovalTicketError("schema_version must be 1")
        _validated_identifier(self.ticket_id, "ticket_id")
        _validated_identifier(self.order_id, "order_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise ApprovalTicketError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise ApprovalTicketError("quantity must be a positive integer")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise ApprovalTicketError("risk_intent must be one of increase or reduce")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        if self.risk_decision_result != "passed":
            raise ApprovalTicketError("risk_decision_result must be passed")
        _validated_identifier(self.oms_transition_reference, "oms_transition_reference")
        if self.oms_state != "PENDING_APPROVAL":
            raise ApprovalTicketError("oms_state must be PENDING_APPROVAL")
        created_at = _parse_timestamp(self.created_at, "created_at")
        expires_at = _parse_timestamp(self.expires_at, "expires_at")
        if expires_at <= created_at:
            raise ApprovalTicketError("expires_at must be after created_at")
        _validated_identifier(self.reason, "reason")
        _assert_json_serializable(self.to_json_dict(), "ticket create request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticket_id": self.ticket_id,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "risk_intent": self.risk_intent,
            "risk_decision_id": self.risk_decision_id,
            "risk_decision_result": self.risk_decision_result,
            "oms_transition_reference": self.oms_transition_reference,
            "oms_state": self.oms_state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApprovalDecisionRequest:
    decision_id: str
    ticket_id: str
    decision: str
    decided_at: str
    actor: str
    decision_reference: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ApprovalTicketError("schema_version must be 1")
        _validated_identifier(self.decision_id, "decision_id")
        _validated_identifier(self.ticket_id, "ticket_id")
        if self.decision not in VALID_DECISIONS:
            raise ApprovalTicketError(
                "decision must be one of approved, rejected, expired, or cancelled"
            )
        _parse_timestamp(self.decided_at, "decided_at")
        _validated_identifier(self.actor, "actor")
        _validated_identifier(self.decision_reference, "decision_reference")
        _validated_identifier(self.reason, "reason")
        _assert_json_serializable(self.to_json_dict(), "decision request")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "ticket_id": self.ticket_id,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "actor": self.actor,
            "decision_reference": self.decision_reference,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApprovalTicket:
    ticket_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    risk_intent: str
    risk_decision_id: str
    oms_transition_reference: str
    status: str
    created_at: str
    expires_at: str
    decision_id: str | None
    decided_at: str | None
    actor: str | None
    decision_reference: str | None
    reason: str | None
    create_request: dict[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ApprovalTicketError("schema_version must be 1")
        _validated_identifier(self.ticket_id, "ticket_id")
        _validated_identifier(self.order_id, "order_id")
        _validated_identifier(self.client_order_id, "client_order_id")
        _validated_symbol(self.symbol, "symbol")
        if self.side not in VALID_SIDES:
            raise ApprovalTicketError("side must be one of buy or sell")
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity < 1
        ):
            raise ApprovalTicketError("quantity must be a positive integer")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise ApprovalTicketError("risk_intent must be one of increase or reduce")
        _validated_identifier(self.risk_decision_id, "risk_decision_id")
        _validated_identifier(self.oms_transition_reference, "oms_transition_reference")
        if self.status not in VALID_TICKET_STATUSES:
            raise ApprovalTicketError(
                "status must be one of pending, approved, rejected, expired, or cancelled"
            )
        created_at = _parse_timestamp(self.created_at, "created_at")
        expires_at = _parse_timestamp(self.expires_at, "expires_at")
        if expires_at <= created_at:
            raise ApprovalTicketError("expires_at must be after created_at")
        if self.status == "pending":
            self._validate_pending_decision_fields()
        else:
            self._validate_completed_decision_fields(expires_at)
        if not isinstance(self.create_request, dict):
            raise ApprovalTicketError("create_request must be a JSON object")
        _assert_json_serializable(self.to_json_dict(), "approval ticket")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticket_id": self.ticket_id,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "risk_intent": self.risk_intent,
            "risk_decision_id": self.risk_decision_id,
            "oms_transition_reference": self.oms_transition_reference,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "decision_id": self.decision_id,
            "decided_at": self.decided_at,
            "actor": self.actor,
            "decision_reference": self.decision_reference,
            "reason": self.reason,
            "create_request": self.create_request,
        }

    @classmethod
    def from_json_dict(cls, raw_ticket: Mapping[str, Any]) -> ApprovalTicket:
        expected_keys = {
            "schema_version",
            "ticket_id",
            "order_id",
            "client_order_id",
            "symbol",
            "side",
            "quantity",
            "risk_intent",
            "risk_decision_id",
            "oms_transition_reference",
            "status",
            "created_at",
            "expires_at",
            "decision_id",
            "decided_at",
            "actor",
            "decision_reference",
            "reason",
            "create_request",
        }
        if not isinstance(raw_ticket, Mapping) or set(raw_ticket) != expected_keys:
            raise ApprovalTicketError("approval ticket fields are invalid")
        create_request = raw_ticket["create_request"]
        if not isinstance(create_request, dict):
            raise ApprovalTicketError("create_request must be a JSON object")
        parsed_create_request = ApprovalTicketCreateRequest(**create_request)
        ticket = cls(
            schema_version=raw_ticket["schema_version"],
            ticket_id=raw_ticket["ticket_id"],
            order_id=raw_ticket["order_id"],
            client_order_id=raw_ticket["client_order_id"],
            symbol=raw_ticket["symbol"],
            side=raw_ticket["side"],
            quantity=raw_ticket["quantity"],
            risk_intent=raw_ticket["risk_intent"],
            risk_decision_id=raw_ticket["risk_decision_id"],
            oms_transition_reference=raw_ticket["oms_transition_reference"],
            status=raw_ticket["status"],
            created_at=raw_ticket["created_at"],
            expires_at=raw_ticket["expires_at"],
            decision_id=raw_ticket["decision_id"],
            decided_at=raw_ticket["decided_at"],
            actor=raw_ticket["actor"],
            decision_reference=raw_ticket["decision_reference"],
            reason=raw_ticket["reason"],
            create_request=create_request,
        )
        if (
            parsed_create_request.ticket_id != ticket.ticket_id
            or parsed_create_request.order_id != ticket.order_id
            or parsed_create_request.client_order_id != ticket.client_order_id
            or parsed_create_request.risk_decision_id != ticket.risk_decision_id
            or parsed_create_request.oms_transition_reference != ticket.oms_transition_reference
            or parsed_create_request.created_at != ticket.created_at
            or parsed_create_request.expires_at != ticket.expires_at
        ):
            raise ApprovalTicketError("approval ticket create_request attribution is inconsistent")
        return ticket

    def _validate_pending_decision_fields(self) -> None:
        if any(
            value is not None
            for value in (
                self.decision_id,
                self.decided_at,
                self.actor,
                self.decision_reference,
                self.reason,
            )
        ):
            raise ApprovalTicketError("pending tickets must not contain decision fields")

    def _validate_completed_decision_fields(self, expires_at: datetime) -> None:
        _validated_identifier(self.decision_id, "decision_id")
        decided_at = _parse_timestamp(self.decided_at, "decided_at")
        _validated_identifier(self.actor, "actor")
        _validated_identifier(self.decision_reference, "decision_reference")
        _validated_identifier(self.reason, "reason")
        if self.status == "expired":
            if decided_at < expires_at:
                raise ApprovalTicketError("expired tickets must be decided at or after expires_at")
            return
        if decided_at > expires_at:
            raise ApprovalTicketError("ticket has expired")


@dataclass(frozen=True)
class ApprovalDecisionRecord:
    decision_id: str
    ticket_id: str
    previous_status: str
    new_status: str
    decided_at: str
    actor: str
    decision_reference: str
    reason: str
    request: dict[str, Any]
    ticket: ApprovalTicket
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ApprovalTicketError("schema_version must be 1")
        _validated_identifier(self.decision_id, "decision_id")
        _validated_identifier(self.ticket_id, "ticket_id")
        if self.previous_status not in VALID_TICKET_STATUSES:
            raise ApprovalTicketError("previous_status must be a known ticket status")
        if self.new_status not in VALID_TICKET_STATUSES - {"pending"}:
            raise ApprovalTicketError("new_status must be a terminal ticket decision")
        _parse_timestamp(self.decided_at, "decided_at")
        _validated_identifier(self.actor, "actor")
        _validated_identifier(self.decision_reference, "decision_reference")
        _validated_identifier(self.reason, "reason")
        if not isinstance(self.request, dict):
            raise ApprovalTicketError("request must be a JSON object")
        if not isinstance(self.ticket, ApprovalTicket):
            raise ApprovalTicketError("ticket must be an ApprovalTicket")
        _assert_json_serializable(self.to_json_dict(), "approval decision record")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "ticket_id": self.ticket_id,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "decided_at": self.decided_at,
            "actor": self.actor,
            "decision_reference": self.decision_reference,
            "reason": self.reason,
            "request": self.request,
            "ticket": self.ticket.to_json_dict(),
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> ApprovalDecisionRecord:
        expected_keys = {
            "schema_version",
            "decision_id",
            "ticket_id",
            "previous_status",
            "new_status",
            "decided_at",
            "actor",
            "decision_reference",
            "reason",
            "request",
            "ticket",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise ApprovalTicketError("approval decision record fields are invalid")
        request = raw_record["request"]
        ticket = raw_record["ticket"]
        if not isinstance(request, dict) or not isinstance(ticket, Mapping):
            raise ApprovalTicketError("approval decision record payloads are invalid")
        parsed_request = ApprovalDecisionRequest(**request)
        parsed_ticket = ApprovalTicket.from_json_dict(ticket)
        record = cls(
            schema_version=raw_record["schema_version"],
            decision_id=raw_record["decision_id"],
            ticket_id=raw_record["ticket_id"],
            previous_status=raw_record["previous_status"],
            new_status=raw_record["new_status"],
            decided_at=raw_record["decided_at"],
            actor=raw_record["actor"],
            decision_reference=raw_record["decision_reference"],
            reason=raw_record["reason"],
            request=request,
            ticket=parsed_ticket,
        )
        if (
            parsed_request.decision_id != record.decision_id
            or parsed_request.ticket_id != record.ticket_id
            or parsed_request.decision != record.new_status
            or parsed_ticket.ticket_id != record.ticket_id
            or parsed_ticket.status != record.new_status
        ):
            raise ApprovalTicketError("approval decision record attribution is inconsistent")
        return record


class ApprovalTicketBook:
    def __init__(self, journal: JsonlEventJournal) -> None:
        self._journal = journal
        self._create_requests: dict[str, dict[str, Any]] = {}
        self._create_tickets: dict[str, ApprovalTicket] = {}
        self._tickets: dict[str, ApprovalTicket] = {}
        self._decision_requests: dict[str, dict[str, Any]] = {}
        self._decision_records: dict[str, ApprovalDecisionRecord] = {}

    def create_ticket(self, request: ApprovalTicketCreateRequest) -> ApprovalTicket:
        if not isinstance(request, ApprovalTicketCreateRequest):
            raise ApprovalTicketError("request must be an ApprovalTicketCreateRequest")

        request_payload = request.to_json_dict()
        if request.ticket_id in self._create_requests:
            if self._create_requests[request.ticket_id] != request_payload:
                raise ApprovalTicketError("conflicting ticket_id")
            return self._create_tickets[request.ticket_id]

        ticket = ApprovalTicket(
            ticket_id=request.ticket_id,
            order_id=request.order_id,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            risk_intent=request.risk_intent,
            risk_decision_id=request.risk_decision_id,
            oms_transition_reference=request.oms_transition_reference,
            status="pending",
            created_at=request.created_at,
            expires_at=request.expires_at,
            decision_id=None,
            decided_at=None,
            actor=None,
            decision_reference=None,
            reason=None,
            create_request=request_payload,
        )
        self._journal.append(
            event_type=APPROVAL_TICKET_CREATED_EVENT_TYPE,
            payload=ticket.to_json_dict(),
            timestamp=ticket.created_at,
        )
        self._create_requests[request.ticket_id] = request_payload
        self._create_tickets[request.ticket_id] = ticket
        self._tickets[request.ticket_id] = ticket
        return ticket

    def restore_pending_ticket(self, ticket: ApprovalTicket) -> None:
        if not isinstance(ticket, ApprovalTicket):
            raise ApprovalTicketError("ticket must be an ApprovalTicket")
        if ticket.status != "pending":
            raise ApprovalTicketError("only pending tickets can be restored")
        if ticket.ticket_id in self._tickets:
            if self._tickets[ticket.ticket_id] != ticket:
                raise ApprovalTicketError("conflicting restored ticket")
            return
        self._create_requests[ticket.ticket_id] = ticket.create_request
        self._create_tickets[ticket.ticket_id] = ticket
        self._tickets[ticket.ticket_id] = ticket

    def apply_decision(self, request: ApprovalDecisionRequest) -> ApprovalDecisionRecord:
        if not isinstance(request, ApprovalDecisionRequest):
            raise ApprovalTicketError("request must be an ApprovalDecisionRequest")

        request_payload = request.to_json_dict()
        if request.decision_id in self._decision_requests:
            if self._decision_requests[request.decision_id] != request_payload:
                raise ApprovalTicketError("conflicting decision_id")
            return self._decision_records[request.decision_id]

        ticket = self.validate_decision(request)

        decided_ticket = self._decided_ticket(ticket, request)
        record = ApprovalDecisionRecord(
            decision_id=request.decision_id,
            ticket_id=request.ticket_id,
            previous_status=ticket.status,
            new_status=request.decision,
            decided_at=request.decided_at,
            actor=request.actor,
            decision_reference=request.decision_reference,
            reason=request.reason,
            request=request_payload,
            ticket=decided_ticket,
        )
        self._journal.append(
            event_type=APPROVAL_DECISION_EVENT_TYPE,
            payload=record.to_json_dict(),
            timestamp=record.decided_at,
        )
        self._tickets[request.ticket_id] = decided_ticket
        self._decision_requests[request.decision_id] = request_payload
        self._decision_records[request.decision_id] = record
        return record

    def validate_decision(self, request: ApprovalDecisionRequest) -> ApprovalTicket:
        if not isinstance(request, ApprovalDecisionRequest):
            raise ApprovalTicketError("request must be an ApprovalDecisionRequest")
        if request.ticket_id not in self._tickets:
            raise ApprovalTicketError("unknown ticket_id")
        ticket = self._tickets[request.ticket_id]
        if ticket.status != "pending":
            raise ApprovalTicketError("ticket is not pending")
        self._validate_decision_timing(request, ticket)
        return ticket

    def current_ticket(self, ticket_id: str) -> ApprovalTicket:
        ticket_id = _validated_identifier(ticket_id, "ticket_id")
        if ticket_id not in self._tickets:
            raise ApprovalTicketError("unknown ticket_id")
        return self._tickets[ticket_id]

    def _validate_decision_timing(
        self,
        request: ApprovalDecisionRequest,
        ticket: ApprovalTicket,
    ) -> None:
        decided_at = _parse_timestamp(request.decided_at, "decided_at")
        expires_at = _parse_timestamp(ticket.expires_at, "expires_at")
        if request.decision == "expired":
            if decided_at < expires_at:
                raise ApprovalTicketError("expired decisions must be at or after expires_at")
            return
        if decided_at > expires_at:
            raise ApprovalTicketError("ticket has expired")

    def _decided_ticket(
        self,
        ticket: ApprovalTicket,
        request: ApprovalDecisionRequest,
    ) -> ApprovalTicket:
        return ApprovalTicket(
            ticket_id=ticket.ticket_id,
            order_id=ticket.order_id,
            client_order_id=ticket.client_order_id,
            symbol=ticket.symbol,
            side=ticket.side,
            quantity=ticket.quantity,
            risk_intent=ticket.risk_intent,
            risk_decision_id=ticket.risk_decision_id,
            oms_transition_reference=ticket.oms_transition_reference,
            status=request.decision,
            created_at=ticket.created_at,
            expires_at=ticket.expires_at,
            decision_id=request.decision_id,
            decided_at=request.decided_at,
            actor=request.actor,
            decision_reference=request.decision_reference,
            reason=request.reason,
            create_request=ticket.create_request,
        )


def _validated_identifier(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalTicketError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ApprovalTicketError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_symbol(symbol: str, field_name: str) -> str:
    _validated_identifier(symbol, field_name)
    if symbol != symbol.upper():
        raise ApprovalTicketError(f"{field_name} must be uppercase")
    return symbol


def _parse_timestamp(value: str | None, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalTicketError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApprovalTicketError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApprovalTicketError(f"{field_name} must include a timezone")
    return parsed


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ApprovalTicketError(f"{payload_name} must be JSON-serializable") from exc
