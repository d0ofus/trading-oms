from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from trading_oms_backend.approval_tickets import (
    ApprovalDecisionRecord,
    ApprovalDecisionRequest,
    ApprovalTicketBook,
    ApprovalTicketCreateRequest,
)
from trading_oms_backend.event_journal import JournalRecord, JsonlEventJournal


class SimulationApprovalServiceError(ValueError):
    """Raised when simulation-only approval decisions cannot be applied safely."""


@dataclass(frozen=True)
class SimulationApprovalDecisionInput:
    decision_id: str
    decided_at: str
    actor: str
    decision_reference: str
    reason: str


class SimulationApprovalService:
    def __init__(self, journal: JsonlEventJournal) -> None:
        if not isinstance(journal, JsonlEventJournal):
            raise SimulationApprovalServiceError("journal must be JsonlEventJournal")
        self._journal = journal
        self._book = ApprovalTicketBook(journal)
        self._seed_demo_ticket()

    def approve(
        self,
        ticket_id: str,
        decision_input: SimulationApprovalDecisionInput,
    ) -> ApprovalDecisionRecord:
        return self._apply_decision(ticket_id, "approved", decision_input)

    def reject(
        self,
        ticket_id: str,
        decision_input: SimulationApprovalDecisionInput,
    ) -> ApprovalDecisionRecord:
        return self._apply_decision(ticket_id, "rejected", decision_input)

    def journal_records(self) -> tuple[JournalRecord, ...]:
        return tuple(self._journal.read_all())

    def _apply_decision(
        self,
        ticket_id: str,
        decision: str,
        decision_input: SimulationApprovalDecisionInput,
    ) -> ApprovalDecisionRecord:
        if not isinstance(decision_input, SimulationApprovalDecisionInput):
            raise SimulationApprovalServiceError(
                "decision_input must be SimulationApprovalDecisionInput"
            )
        return self._book.apply_decision(
            ApprovalDecisionRequest(
                decision_id=decision_input.decision_id,
                ticket_id=ticket_id,
                decision=decision,
                decided_at=decision_input.decided_at,
                actor=decision_input.actor,
                decision_reference=decision_input.decision_reference,
                reason=decision_input.reason,
            ),
        )

    def _seed_demo_ticket(self) -> None:
        self._book.create_ticket(
            ApprovalTicketCreateRequest(
                ticket_id="approval-ticket-001",
                order_id="order-001",
                client_order_id="client-001",
                symbol="AAPL",
                side="buy",
                quantity=10,
                risk_intent="increase",
                risk_decision_id="risk-001",
                risk_decision_result="passed",
                oms_transition_reference="order-001-pending-approval",
                oms_state="PENDING_APPROVAL",
                created_at="2026-07-08T13:45:10Z",
                expires_at="2026-07-08T13:50:10Z",
                reason="risk_passed_requires_human_approval",
            ),
        )


_approval_temp_dir: TemporaryDirectory[str] | None = None
_approval_service: SimulationApprovalService | None = None


def get_simulation_approval_service() -> SimulationApprovalService:
    global _approval_service
    if _approval_service is None:
        _approval_service = _build_service()
    return _approval_service


def reset_simulation_approval_service() -> SimulationApprovalService:
    global _approval_service
    _approval_service = _build_service()
    return _approval_service


def _build_service() -> SimulationApprovalService:
    global _approval_temp_dir
    if _approval_temp_dir is None:
        _approval_temp_dir = tempfile.TemporaryDirectory(prefix="trading-oms-approval-")
    journal_path = Path(_approval_temp_dir.name) / "simulation-approval-journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    return SimulationApprovalService(JsonlEventJournal(journal_path))
