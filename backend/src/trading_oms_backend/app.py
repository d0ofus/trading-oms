from __future__ import annotations

import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from trading_oms_backend.audit_export import AuditExportError, build_audit_export_bundle
from trading_oms_backend.config import get_settings
from trading_oms_backend.emergency_stop import (
    EmergencyStopChangeRequest,
    EmergencyStopError,
    EmergencyStopService,
)
from trading_oms_backend.event_journal import JournalRecord, JsonlEventJournal
from trading_oms_backend.operator_auth import (
    ADMINISTER_SYSTEM_PERMISSION,
    APPROVE_SIMULATION_PERMISSION,
    VIEW_OPERATIONS_PERMISSION,
    OperatorAuthError,
    OperatorIdentity,
    authorize_operator,
    operator_identity_from_headers,
)
from trading_oms_backend.read_models import (
    EmergencyStopReadModel,
    OperationsReadModel,
    OperatorSessionReadModel,
    build_demo_operations_read_model,
)
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


class EmergencyStopChangeBody(BaseModel):
    event_id: str
    requested_at: str
    actor: str
    reason: str
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


@app.get("/api/operator-session")
def get_operator_session(request: Request) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="operator_session",
        action="view",
    )
    return OperatorSessionReadModel.from_identity(identity).to_json_dict()


@app.get("/api/emergency-stop")
def get_emergency_stop(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="emergency_stop",
        action="view",
    )
    return _emergency_stop_read_model().to_json_dict()


@app.get("/api/safety")
def get_safety(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="safety_posture",
        action="view",
    )
    return _operations_read_model().safety.to_json_dict()


@app.get("/api/audit-events")
def get_audit_events(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="audit_events",
        action="view",
    )
    return [event.to_json_dict() for event in _operations_read_model().audit_events]


@app.get("/api/signals")
def get_signals(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="signals",
        action="view",
    )
    return [signal.to_json_dict() for signal in _operations_read_model().signals]


@app.get("/api/risk-decisions")
def get_risk_decisions(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="risk_decisions",
        action="view",
    )
    return [decision.to_json_dict() for decision in _operations_read_model().risk_decisions]


@app.get("/api/approval-tickets")
def get_approval_tickets(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="approval_tickets",
        action="view",
    )
    return [ticket.to_json_dict() for ticket in _operations_read_model().approval_tickets]


@app.get("/api/orders")
def get_orders(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="orders",
        action="view",
    )
    return [order.to_json_dict() for order in _operations_read_model().orders]


@app.get("/api/positions")
def get_positions(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="positions",
        action="view",
    )
    return [position.to_json_dict() for position in _operations_read_model().positions]


@app.get("/api/alerts")
def get_alerts(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="alerts",
        action="view",
    )
    return [alert.to_json_dict() for alert in _operations_read_model().alerts]


@app.get("/api/readiness")
def get_readiness(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="readiness",
        action="view",
    )
    return _operations_read_model().readiness.to_json_dict()


@app.get("/api/paper-trading")
def get_paper_trading(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="paper_trading",
        action="view",
    )
    return _operations_read_model().paper_trading.to_json_dict()


@app.get("/api/operational-controls")
def get_operational_controls(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="operational_controls",
        action="view",
    )
    return _operations_read_model().operational_controls.to_json_dict()


@app.get("/api/live-readiness-evidence")
def get_live_readiness_evidence(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="live_readiness_evidence",
        action="view",
    )
    return _operations_read_model().live_readiness_evidence.to_json_dict()


@app.get("/api/audit-export-bundle")
def get_audit_export_bundle(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="audit_export_bundle",
        action="view",
    )
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
def list_workflows(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_definitions",
        action="view",
    )
    return [record.to_json_dict() for record in get_workflow_definition_store().list_workflows()]


@app.post("/api/workflows")
def create_workflow(request: Request, definition: WorkflowDefinitionBody) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=ADMINISTER_SYSTEM_PERMISSION,
        resource="workflow_definition",
        action="create",
    )
    try:
        request = _workflow_definition_request(definition)
        record = get_workflow_definition_store().create_workflow(request)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_json_dict()


@app.get("/api/workflows/{workflow_id}")
def get_workflow(request: Request, workflow_id: str) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_definition",
        action="view",
    )
    try:
        record = get_workflow_definition_store().get_workflow(workflow_id)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.to_json_dict()


@app.post("/api/workflows/{workflow_id}/simulation-runs")
def start_workflow_simulation_run(
    request: Request,
    workflow_id: str,
    run: WorkflowSimulationRunBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=ADMINISTER_SYSTEM_PERMISSION,
        resource="workflow_simulation_run",
        action="start",
    )
    try:
        request = _workflow_simulation_run_request(run)
        record = get_workflow_simulation_runner().start_run(
            workflow_id,
            request,
            requested_by=identity.operator_id,
        )
    except WorkflowSimulationRunError as exc:
        if "emergency stop is active" in str(exc):
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        status_code = 404 if "unknown workflow_id" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return record.to_json_dict()


@app.get("/api/workflows/{workflow_id}/simulation-runs")
def list_workflow_simulation_runs(request: Request, workflow_id: str) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_simulation_runs",
        action="view",
    )
    return [
        record.to_json_dict() for record in get_workflow_simulation_runner().list_runs(workflow_id)
    ]


@app.get("/api/workflows/{workflow_id}/simulation-runs/{run_id}")
def get_workflow_simulation_run(request: Request, workflow_id: str, run_id: str) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_simulation_run",
        action="view",
    )
    try:
        record = get_workflow_simulation_runner().get_run(workflow_id, run_id)
    except WorkflowSimulationRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.to_json_dict()


@app.put("/api/workflows/{workflow_id}")
def update_workflow(
    request: Request,
    workflow_id: str,
    definition: WorkflowDefinitionBody,
) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=ADMINISTER_SYSTEM_PERMISSION,
        resource="workflow_definition",
        action="update",
    )
    try:
        request = _workflow_definition_request(definition)
        record = get_workflow_definition_store().update_workflow(workflow_id, request)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_json_dict()


@app.post("/api/emergency-stop/activate")
def activate_emergency_stop(
    request: Request,
    change: EmergencyStopChangeBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=ADMINISTER_SYSTEM_PERMISSION,
        resource="emergency_stop",
        action="activate",
    )
    return _apply_emergency_stop_change("activate", change, identity)


@app.post("/api/emergency-stop/deactivate")
def deactivate_emergency_stop(
    request: Request,
    change: EmergencyStopChangeBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=ADMINISTER_SYSTEM_PERMISSION,
        resource="emergency_stop",
        action="deactivate",
    )
    return _apply_emergency_stop_change("deactivate", change, identity)


@app.post("/api/approval-tickets/{ticket_id}/approve")
def approve_simulation_ticket(
    request: Request,
    ticket_id: str,
    decision: ApprovalDecisionBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=APPROVE_SIMULATION_PERMISSION,
        resource=f"approval_ticket.{ticket_id}",
        action="approve",
    )
    return _apply_simulation_approval_decision(ticket_id, "approved", decision, identity)


@app.post("/api/approval-tickets/{ticket_id}/reject")
def reject_simulation_ticket(
    request: Request,
    ticket_id: str,
    decision: ApprovalDecisionBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=APPROVE_SIMULATION_PERMISSION,
        resource=f"approval_ticket.{ticket_id}",
        action="reject",
    )
    return _apply_simulation_approval_decision(ticket_id, "rejected", decision, identity)


def _operations_read_model() -> OperationsReadModel:
    return build_demo_operations_read_model(
        get_settings(),
        emergency_stop=_emergency_stop_read_model(),
    )


def _emergency_stop_read_model() -> EmergencyStopReadModel:
    state = get_emergency_stop_service().current_state()
    return EmergencyStopReadModel(
        active=state.active,
        status=state.status,
        updated_at=state.updated_at,
        activated_at=state.activated_at,
        activated_by=state.activated_by,
        activation_reason=state.activation_reason,
        deactivated_at=state.deactivated_at,
        deactivated_by=state.deactivated_by,
        deactivation_reason=state.deactivation_reason,
        blocking_risk_increasing_actions=state.blocking_risk_increasing_actions,
    )


def reset_simulation_approval_service() -> None:
    _reset_simulation_approval_service()


_operator_auth_temp_dir: TemporaryDirectory[str] | None = None
_operator_auth_journal: JsonlEventJournal | None = None
_emergency_stop_temp_dir: TemporaryDirectory[str] | None = None
_emergency_stop_journal: JsonlEventJournal | None = None
_emergency_stop_service: EmergencyStopService | None = None
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


def get_operator_auth_journal() -> JsonlEventJournal:
    global _operator_auth_journal
    if _operator_auth_journal is None:
        _operator_auth_journal = _build_operator_auth_journal()
    return _operator_auth_journal


def get_emergency_stop_service() -> EmergencyStopService:
    global _emergency_stop_service
    if _emergency_stop_service is None:
        _emergency_stop_service = _build_emergency_stop_service()
    return _emergency_stop_service


def get_emergency_stop_journal() -> JsonlEventJournal:
    global _emergency_stop_journal
    if _emergency_stop_journal is None:
        _emergency_stop_journal = _build_emergency_stop_journal()
    return _emergency_stop_journal


def reset_emergency_stop_service() -> EmergencyStopService:
    global _emergency_stop_journal, _emergency_stop_service, _workflow_simulation_runner
    _emergency_stop_journal = _build_emergency_stop_journal()
    _emergency_stop_service = EmergencyStopService(_emergency_stop_journal)
    _workflow_simulation_runner = None
    return _emergency_stop_service


def emergency_stop_journal_records() -> tuple[JournalRecord, ...]:
    return tuple(get_emergency_stop_journal().read_all())


def reset_operator_auth_service() -> JsonlEventJournal:
    global _operator_auth_journal
    _operator_auth_journal = _build_operator_auth_journal()
    return _operator_auth_journal


def operator_auth_journal_records() -> tuple[JournalRecord, ...]:
    return tuple(get_operator_auth_journal().read_all())


def reset_workflow_simulation_runner_service() -> WorkflowSimulationRunner:
    global _workflow_simulation_runner
    _workflow_simulation_runner = _build_workflow_simulation_runner()
    return _workflow_simulation_runner


def _apply_simulation_approval_decision(
    ticket_id: str,
    action: str,
    decision: ApprovalDecisionBody,
    identity: OperatorIdentity,
) -> dict[str, Any]:
    if decision.actor != identity.operator_id:
        raise HTTPException(
            status_code=400,
            detail="actor must match authenticated operator",
        )
    if action == "approved":
        try:
            get_emergency_stop_service().ensure_risk_increasing_allowed(
                resource=f"approval_ticket.{ticket_id}",
                action="approve",
                checked_at=decision.decided_at,
                actor=identity.operator_id,
            )
        except EmergencyStopError as exc:
            raise HTTPException(status_code=423, detail=str(exc)) from exc
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


def _apply_emergency_stop_change(
    action: str,
    change: EmergencyStopChangeBody,
    identity: OperatorIdentity,
) -> dict[str, Any]:
    if change.actor != identity.operator_id:
        raise HTTPException(
            status_code=400,
            detail="actor must match authenticated operator",
        )
    try:
        request = EmergencyStopChangeRequest(
            schema_version=change.schema_version,
            event_id=change.event_id,
            requested_at=change.requested_at,
            actor=change.actor,
            reason=change.reason,
        )
        if action == "activate":
            record = get_emergency_stop_service().activate(request)
        else:
            record = get_emergency_stop_service().deactivate(request)
    except EmergencyStopError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.to_json_dict()


def _authorize_request(
    request: Request,
    *,
    permission: str,
    resource: str,
    action: str,
) -> OperatorIdentity:
    try:
        identity = operator_identity_from_headers(request.headers, settings=get_settings())
        decision = authorize_operator(
            identity,
            permission=permission,
            resource=resource,
            action=action,
            journal=get_operator_auth_journal(),
        )
    except OperatorAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if decision.result != "allowed":
        raise HTTPException(
            status_code=403,
            detail=f"operator lacks required permission: {permission}",
        )
    return identity


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


def _build_operator_auth_journal() -> JsonlEventJournal:
    global _operator_auth_temp_dir
    if _operator_auth_temp_dir is None:
        _operator_auth_temp_dir = tempfile.TemporaryDirectory(prefix="trading-oms-authz-")
    journal_path = Path(_operator_auth_temp_dir.name) / "operator-authz-journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    return JsonlEventJournal(journal_path)


def _build_emergency_stop_journal() -> JsonlEventJournal:
    global _emergency_stop_temp_dir
    if _emergency_stop_temp_dir is None:
        _emergency_stop_temp_dir = tempfile.TemporaryDirectory(prefix="trading-oms-emergency-stop-")
    journal_path = Path(_emergency_stop_temp_dir.name) / "emergency-stop-journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    return JsonlEventJournal(journal_path)


def _build_emergency_stop_service() -> EmergencyStopService:
    return EmergencyStopService(get_emergency_stop_journal())


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
        get_workflow_definition_store(),
        JsonlEventJournal(journal_path),
        emergency_stop_service=get_emergency_stop_service(),
    )
