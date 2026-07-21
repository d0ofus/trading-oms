from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_oms_backend.event_journal import JsonlEventJournal

ORDER_INTENT_PROPOSED_EVENT_TYPE = "order_intent.proposed"
NON_ROUTABLE_STATUS = "proposed_non_routable"
VALID_ORDER_TYPES = {"market", "limit"}
VALID_RISK_INTENTS = {"increase", "reduce"}
VALID_SIDES = {"buy", "sell"}
FORBIDDEN_REFERENCE_FRAGMENTS = {
    "://",
    "account",
    "api_key",
    "authorization",
    "broker",
    "credential",
    "ibkr",
    "password",
    "private_key",
    "secret",
    "socket",
    "token",
    "transmit",
}


class OrderIntentError(ValueError):
    """Raised when order-intent proposal records are invalid."""


@dataclass(frozen=True)
class OrderIntentProtectivePlan:
    kind: str
    stop_price: float
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OrderIntentError("schema_version must be 1")
        _validated_identifier(self.kind, "kind")
        _positive_finite_number(self.stop_price, "stop_price")
        _assert_json_serializable(self.to_json_dict(), "protective plan")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "stop_price": self.stop_price,
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> OrderIntentProtectivePlan:
        if not isinstance(raw_record, Mapping) or set(raw_record) != {
            "schema_version",
            "kind",
            "stop_price",
        }:
            raise OrderIntentError("protective plan fields are invalid")
        return cls(**dict(raw_record))


@dataclass(frozen=True)
class OrderIntentProposalRequest:
    proposal_id: str
    source_signal_reference: str
    symbol: str
    side: str
    risk_intent: str
    quantity: int
    order_type: str
    reference_price: float
    proposed_at: str
    protective_order_plan: OrderIntentProtectivePlan | None = None
    protective_exception_reference: str | None = None
    limit_price: float | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise OrderIntentError("schema_version must be 1")
        _validated_safe_identifier(self.proposal_id, "proposal_id")
        _validated_safe_identifier(self.source_signal_reference, "source_signal_reference")
        _validated_symbol(self.symbol)
        if self.side not in VALID_SIDES:
            raise OrderIntentError("side must be one of buy or sell")
        if self.risk_intent not in VALID_RISK_INTENTS:
            raise OrderIntentError("risk_intent must be one of increase or reduce")
        _positive_integer(self.quantity, "quantity")
        if self.order_type not in VALID_ORDER_TYPES:
            raise OrderIntentError("order_type must be one of market or limit")
        _positive_finite_number(self.reference_price, "reference_price")
        _parse_timestamp(self.proposed_at, "proposed_at")
        self._validate_limit_price()
        self._validate_protection()
        _assert_json_serializable(self.to_payload(), "order-intent proposal request")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "source_signal_reference": self.source_signal_reference,
            "symbol": self.symbol,
            "side": self.side,
            "risk_intent": self.risk_intent,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "reference_price": self.reference_price,
            "limit_price": self.limit_price,
            "proposed_at": self.proposed_at,
            "protective_order_plan": (
                None
                if self.protective_order_plan is None
                else self.protective_order_plan.to_json_dict()
            ),
            "protective_exception_reference": self.protective_exception_reference,
        }

    def _validate_limit_price(self) -> None:
        if self.order_type == "market":
            if self.limit_price is not None:
                raise OrderIntentError("limit_price must be omitted for market proposals")
            return
        if self.limit_price is None:
            raise OrderIntentError("limit_price is required for limit proposals")
        _positive_finite_number(self.limit_price, "limit_price")

    def _validate_protection(self) -> None:
        if self.protective_order_plan is not None and not isinstance(
            self.protective_order_plan,
            OrderIntentProtectivePlan,
        ):
            raise OrderIntentError("protective_order_plan must be an OrderIntentProtectivePlan")
        if self.protective_exception_reference is not None:
            _validated_safe_identifier(
                self.protective_exception_reference,
                "protective_exception_reference",
            )
        if self.protective_order_plan is not None and self.protective_exception_reference:
            raise OrderIntentError(
                "protective_order_plan and protective_exception_reference are mutually exclusive"
            )
        if self.risk_intent == "reduce":
            return
        if self.protective_order_plan is None and self.protective_exception_reference is None:
            raise OrderIntentError(
                "risk-increasing order-intent proposals require a protective plan or exception"
            )
        if self.protective_order_plan is None:
            return
        if self.side == "buy" and self.protective_order_plan.stop_price >= self.reference_price:
            raise OrderIntentError("buy protective stop must be below reference_price")
        if self.side == "sell" and self.protective_order_plan.stop_price <= self.reference_price:
            raise OrderIntentError("sell protective stop must be above reference_price")


@dataclass(frozen=True)
class OrderIntentProposal:
    proposal_id: str
    status: str
    source_signal_reference: str
    symbol: str
    side: str
    risk_intent: str
    quantity: int
    order_type: str
    reference_price: float
    proposed_at: str
    protective_order_plan: OrderIntentProtectivePlan | None
    protective_exception_reference: str | None
    journal_references: tuple[str, ...]
    limit_price: float | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        request = OrderIntentProposalRequest(
            proposal_id=self.proposal_id,
            source_signal_reference=self.source_signal_reference,
            symbol=self.symbol,
            side=self.side,
            risk_intent=self.risk_intent,
            quantity=self.quantity,
            order_type=self.order_type,
            reference_price=self.reference_price,
            proposed_at=self.proposed_at,
            protective_order_plan=self.protective_order_plan,
            protective_exception_reference=self.protective_exception_reference,
            limit_price=self.limit_price,
            schema_version=self.schema_version,
        )
        if self.status != NON_ROUTABLE_STATUS:
            raise OrderIntentError("order-intent proposal status must be non-routable")
        _validated_journal_references(self.journal_references)
        _assert_json_serializable(self.to_json_dict(), "order-intent proposal")
        request.to_payload()

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "status": self.status,
            "source_signal_reference": self.source_signal_reference,
            "symbol": self.symbol,
            "side": self.side,
            "risk_intent": self.risk_intent,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "reference_price": self.reference_price,
            "limit_price": self.limit_price,
            "proposed_at": self.proposed_at,
            "protective_order_plan": (
                None
                if self.protective_order_plan is None
                else self.protective_order_plan.to_json_dict()
            ),
            "protective_exception_reference": self.protective_exception_reference,
            "journal_references": list(self.journal_references),
        }

    @classmethod
    def from_json_dict(cls, raw_record: Mapping[str, Any]) -> OrderIntentProposal:
        expected_keys = {
            "schema_version",
            "proposal_id",
            "status",
            "source_signal_reference",
            "symbol",
            "side",
            "risk_intent",
            "quantity",
            "order_type",
            "reference_price",
            "limit_price",
            "proposed_at",
            "protective_order_plan",
            "protective_exception_reference",
            "journal_references",
        }
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_keys:
            raise OrderIntentError("order-intent proposal fields are invalid")
        raw_plan = raw_record["protective_order_plan"]
        if raw_plan is not None and not isinstance(raw_plan, Mapping):
            raise OrderIntentError("protective_order_plan must be an object or null")
        references = raw_record["journal_references"]
        if not isinstance(references, list):
            raise OrderIntentError("journal_references must be a list")
        return cls(
            schema_version=raw_record["schema_version"],
            proposal_id=raw_record["proposal_id"],
            status=raw_record["status"],
            source_signal_reference=raw_record["source_signal_reference"],
            symbol=raw_record["symbol"],
            side=raw_record["side"],
            risk_intent=raw_record["risk_intent"],
            quantity=raw_record["quantity"],
            order_type=raw_record["order_type"],
            reference_price=raw_record["reference_price"],
            limit_price=raw_record["limit_price"],
            proposed_at=raw_record["proposed_at"],
            protective_order_plan=(
                None if raw_plan is None else OrderIntentProtectivePlan.from_json_dict(raw_plan)
            ),
            protective_exception_reference=raw_record["protective_exception_reference"],
            journal_references=tuple(references),
        )


class OrderIntentProposalBook:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise OrderIntentError("journal must be JsonlEventJournal")
        self._journal = journal
        self._proposals: dict[str, OrderIntentProposal] = {}
        self._payloads: dict[str, dict[str, Any]] = {}
        self._source_signal_proposals: dict[str, str] = {}

    def propose(self, request: OrderIntentProposalRequest) -> OrderIntentProposal:
        if not isinstance(request, OrderIntentProposalRequest):
            raise OrderIntentError("request must be OrderIntentProposalRequest")

        request_payload = request.to_payload()
        existing_payload = self._payloads.get(request.proposal_id)
        if existing_payload is not None:
            if existing_payload != request_payload:
                raise OrderIntentError("conflicting duplicate proposal_id")
            return self._proposals[request.proposal_id]

        existing_source_proposal_id = self._source_signal_proposals.get(
            request.source_signal_reference
        )
        if existing_source_proposal_id is not None:
            raise OrderIntentError(
                f"source signal already has proposal {existing_source_proposal_id}"
            )

        journal_reference = _journal_reference(self._next_journal_sequence())
        proposal = OrderIntentProposal(
            proposal_id=request.proposal_id,
            status=NON_ROUTABLE_STATUS,
            source_signal_reference=request.source_signal_reference,
            symbol=request.symbol,
            side=request.side,
            risk_intent=request.risk_intent,
            quantity=request.quantity,
            order_type=request.order_type,
            reference_price=request.reference_price,
            limit_price=request.limit_price,
            proposed_at=request.proposed_at,
            protective_order_plan=request.protective_order_plan,
            protective_exception_reference=request.protective_exception_reference,
            journal_references=(journal_reference,),
        )
        self._journal.append(
            event_type=ORDER_INTENT_PROPOSED_EVENT_TYPE,
            payload=proposal.to_json_dict(),
            timestamp=proposal.proposed_at,
        )
        self._proposals[request.proposal_id] = proposal
        self._payloads[request.proposal_id] = request_payload
        self._source_signal_proposals[request.source_signal_reference] = request.proposal_id
        return proposal

    def get_proposal(self, proposal_id: str) -> OrderIntentProposal:
        _validated_safe_identifier(proposal_id, "proposal_id")
        try:
            return self._proposals[proposal_id]
        except KeyError as exc:
            raise OrderIntentError("unknown proposal_id") from exc

    def list_proposals(self) -> tuple[OrderIntentProposal, ...]:
        return tuple(self._proposals.values())

    def _next_journal_sequence(self) -> int:
        records = self._journal.read_all()
        return records[-1].sequence + 1 if records else 1


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrderIntentError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise OrderIntentError(f"{field_name} must not contain leading or trailing whitespace")
    return value


def _validated_safe_identifier(value: str, field_name: str) -> str:
    _validated_identifier(value, field_name)
    normalized = value.lower()
    if any(fragment in normalized for fragment in FORBIDDEN_REFERENCE_FRAGMENTS):
        raise OrderIntentError(f"{field_name} must not contain unsafe broker or secret references")
    return value


def _validated_symbol(symbol: str) -> str:
    _validated_identifier(symbol, "symbol")
    if symbol != symbol.upper():
        raise OrderIntentError("symbol must be uppercase")
    return symbol


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OrderIntentError(f"{field_name} must be a positive integer")
    return value


def _positive_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise OrderIntentError(f"{field_name} must be a finite number")

    number = float(value)
    if not math.isfinite(number):
        raise OrderIntentError(f"{field_name} must be a finite number")
    if number <= 0:
        raise OrderIntentError(f"{field_name} must be greater than zero")
    return number


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OrderIntentError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrderIntentError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OrderIntentError(f"{field_name} must include a timezone")
    return parsed


def _validated_journal_references(references: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(references, tuple) or not references:
        raise OrderIntentError("journal_references must be a non-empty tuple")
    for reference in references:
        _validated_identifier(reference, "journal_references")
        if not reference.startswith("journal_sequence:"):
            raise OrderIntentError("journal_references must use journal_sequence references")
    return references


def _journal_reference(sequence: int) -> str:
    return f"journal_sequence:{sequence}"


def _assert_json_serializable(payload: dict[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OrderIntentError(f"{payload_name} must be JSON-serializable") from exc
