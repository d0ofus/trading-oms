from __future__ import annotations

import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from trading_oms_backend.audit_export import AuditExportError, build_audit_export_bundle
from trading_oms_backend.config import get_settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.read_models import OperationsReadModel, build_demo_operations_read_model
from trading_oms_backend.simulation_approval_service import (
    SimulationApprovalDecisionInput,
    get_simulation_approval_service,
)
from trading_oms_backend.simulation_approval_service import (
    reset_simulation_approval_service as _reset_simulation_approval_service,
)
from trading_oms_backend.workflow_definitions import (
    WorkflowDefinitionError,
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionStore,
)
from trading_oms_backend.workflow_simulation_runs import (
    WorkflowSimulationRunError,
    WorkflowSimulationRunner,
    WorkflowSimulationRunRequest,
)

app = FastAPI(title="Trading OMS", version="0.1.0")


class ApprovalDecisionBody(BaseModel):
    decision_id: str
    decided_at: str
    actor: str
    decision_reference: str
    reason: str


class WorkflowDefinitionBody(BaseModel):
    workflow_id: str
    display_name: str
    description: str
    requested_at: str
    document: dict[str, Any]
    schema_version: int = 1


class WorkflowSimulationRunBody(BaseModel):
    run_id: str
    requested_at: str
    evaluated_at: str
    approval_expires_at: str
    replay_input_reference: str
    schema_version: int = 1


@app.get("/healthz")
def healthz() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "app_mode": settings.app_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "ibkr_account_mode": settings.ibkr_account_mode,
        "broker_connectivity": "not_configured",
    }


@app.get("/api/safety")
def get_safety() -> dict[str, Any]:
    return _operations_read_model().safety.to_json_dict()


@app.get("/api/audit-events")
def get_audit_events() -> list[dict[str, Any]]:
    return [event.to_json_dict() for event in _operations_read_model().audit_events]


@app.get("/api/signals")
def get_signals() -> list[dict[str, Any]]:
    return [signal.to_json_dict() for signal in _operations_read_model().signals]


@app.get("/api/risk-decisions")
def get_risk_decisions() -> list[dict[str, Any]]:
    return [decision.to_json_dict() for decision in _operations_read_model().risk_decisions]


@app.get("/api/approval-tickets")
def get_approval_tickets() -> list[dict[str, Any]]:
    return [ticket.to_json_dict() for ticket in _operations_read_model().approval_tickets]


@app.get("/api/orders")
def get_orders() -> list[dict[str, Any]]:
    return [order.to_json_dict() for order in _operations_read_model().orders]


@app.get("/api/positions")
def get_positions() -> list[dict[str, Any]]:
    return [position.to_json_dict() for position in _operations_read_model().positions]


@app.get("/api/alerts")
def get_alerts() -> list[dict[str, Any]]:
    return [alert.to_json_dict() for alert in _operations_read_model().alerts]


@app.get("/api/readiness")
def get_readiness() -> dict[str, Any]:
    return _operations_read_model().readiness.to_json_dict()


@app.get("/api/paper-trading")
def get_paper_trading() -> dict[str, Any]:
    return _operations_read_model().paper_trading.to_json_dict()


@app.get("/api/audit-export-bundle")
def get_audit_export_bundle() -> dict[str, Any]:
    try:
        workflows = get_workflow_definition_store().list_workflows()
        runner = get_workflow_simulation_runner()
        runs = tuple(
            run for workflow in workflows for run in runner.list_runs(workflow.workflow_id)
        )
        bundle = build_audit_export_bundle(
            export_id="audit-export-local-review",
            generated_at="2026-07-08T13:46:00Z",
            review_reference="local-human-review",
            operations_read_model=_operations_read_model(),
            workflow_definitions=workflows,
            workflow_simulation_runs=runs,
            journal_records=runner.journal_records(),
        )
    except AuditExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return bundle.to_json_dict()


@app.get("/api/workflows")
def list_workflows() -> list[dict[str, Any]]:
    return [record.to_json_dict() for record in get_workflow_definition_store().list_workflows()]


@app.post("/api/workflows")
def create_workflow(definition: WorkflowDefinitionBody) -> dict[str, Any]:
    try:
        request = _workflow_definition_request(definition)
        record = get_workflow_definition_store().create_workflow(request)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_json_dict()


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    try:
        record = get_workflow_definition_store().get_workflow(workflow_id)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.to_json_dict()


@app.post("/api/workflows/{workflow_id}/simulation-runs")
def start_workflow_simulation_run(
    workflow_id: str,
    run: WorkflowSimulationRunBody,
) -> dict[str, Any]:
    try:
        request = _workflow_simulation_run_request(run)
        record = get_workflow_simulation_runner().start_run(workflow_id, request)
    except WorkflowSimulationRunError as exc:
        status_code = 404 if "unknown workflow_id" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return record.to_json_dict()


@app.get("/api/workflows/{workflow_id}/simulation-runs")
def list_workflow_simulation_runs(workflow_id: str) -> list[dict[str, Any]]:
    return [
        record.to_json_dict() for record in get_workflow_simulation_runner().list_runs(workflow_id)
    ]


@app.get("/api/workflows/{workflow_id}/simulation-runs/{run_id}")
def get_workflow_simulation_run(workflow_id: str, run_id: str) -> dict[str, Any]:
    try:
        record = get_workflow_simulation_runner().get_run(workflow_id, run_id)
    except WorkflowSimulationRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.to_json_dict()


@app.put("/api/workflows/{workflow_id}")
def update_workflow(workflow_id: str, definition: WorkflowDefinitionBody) -> dict[str, Any]:
    try:
        request = _workflow_definition_request(definition)
        record = get_workflow_definition_store().update_workflow(workflow_id, request)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_json_dict()


@app.post("/api/approval-tickets/{ticket_id}/approve")
def approve_simulation_ticket(
    ticket_id: str,
    decision: ApprovalDecisionBody,
) -> dict[str, Any]:
    return _apply_simulation_approval_decision(ticket_id, "approved", decision)


@app.post("/api/approval-tickets/{ticket_id}/reject")
def reject_simulation_ticket(
    ticket_id: str,
    decision: ApprovalDecisionBody,
) -> dict[str, Any]:
    return _apply_simulation_approval_decision(ticket_id, "rejected", decision)


def _operations_read_model() -> OperationsReadModel:
    return build_demo_operations_read_model(get_settings())


def reset_simulation_approval_service() -> None:
    _reset_simulation_approval_service()


_workflow_temp_dir: TemporaryDirectory[str] | None = None
_workflow_store: WorkflowDefinitionStore | None = None
_workflow_simulation_temp_dir: TemporaryDirectory[str] | None = None
_workflow_simulation_runner: WorkflowSimulationRunner | None = None


def get_workflow_definition_store() -> WorkflowDefinitionStore:
    global _workflow_store
    if _workflow_store is None:
        _workflow_store = _build_workflow_definition_store()
    return _workflow_store


def reset_workflow_definition_service() -> WorkflowDefinitionStore:
    global _workflow_simulation_runner, _workflow_store
    _workflow_store = _build_workflow_definition_store()
    _workflow_simulation_runner = None
    return _workflow_store


def get_workflow_simulation_runner() -> WorkflowSimulationRunner:
    global _workflow_simulation_runner
    if _workflow_simulation_runner is None:
        _workflow_simulation_runner = _build_workflow_simulation_runner()
    return _workflow_simulation_runner


def reset_workflow_simulation_runner_service() -> WorkflowSimulationRunner:
    global _workflow_simulation_runner
    _workflow_simulation_runner = _build_workflow_simulation_runner()
    return _workflow_simulation_runner


def _apply_simulation_approval_decision(
    ticket_id: str,
    action: str,
    decision: ApprovalDecisionBody,
) -> dict[str, Any]:
    service = get_simulation_approval_service()
    decision_input = SimulationApprovalDecisionInput(
        decision_id=decision.decision_id,
        decided_at=decision.decided_at,
        actor=decision.actor,
        decision_reference=decision.decision_reference,
        reason=decision.reason,
    )
    try:
        if action == "approved":
            record = service.approve(ticket_id, decision_input)
        else:
            record = service.reject(ticket_id, decision_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_json_dict()


def _workflow_definition_request(
    definition: WorkflowDefinitionBody,
) -> WorkflowDefinitionSaveRequest:
    return WorkflowDefinitionSaveRequest(
        schema_version=definition.schema_version,
        workflow_id=definition.workflow_id,
        display_name=definition.display_name,
        description=definition.description,
        document=definition.document,
        requested_at=definition.requested_at,
    )


def _workflow_simulation_run_request(
    run: WorkflowSimulationRunBody,
) -> WorkflowSimulationRunRequest:
    return WorkflowSimulationRunRequest(
        schema_version=run.schema_version,
        run_id=run.run_id,
        requested_at=run.requested_at,
        evaluated_at=run.evaluated_at,
        approval_expires_at=run.approval_expires_at,
        replay_input_reference=run.replay_input_reference,
    )


def _build_workflow_definition_store() -> WorkflowDefinitionStore:
    global _workflow_temp_dir
    if _workflow_temp_dir is None:
        _workflow_temp_dir = tempfile.TemporaryDirectory(prefix="trading-oms-workflows-")
    store_path = Path(_workflow_temp_dir.name) / "workflow-definitions.json"
    if store_path.exists():
        store_path.unlink()
    return WorkflowDefinitionStore(store_path)


def _build_workflow_simulation_runner() -> WorkflowSimulationRunner:
    global _workflow_simulation_temp_dir
    if _workflow_simulation_temp_dir is None:
        _workflow_simulation_temp_dir = tempfile.TemporaryDirectory(
            prefix="trading-oms-workflow-runs-"
        )
    journal_path = Path(_workflow_simulation_temp_dir.name) / "workflow-simulation-journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    return WorkflowSimulationRunner(
        get_workflow_definition_store(), JsonlEventJournal(journal_path)
    )
