from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from trading_oms_backend.emergency_stop import EmergencyStopError
from trading_oms_backend.event_journal import JournalError, JsonlEventJournal
from trading_oms_backend.operator_auth import (
    AUTHOR_STRATEGY_PERMISSION,
    OPERATE_STRATEGY_PERMISSION,
    VIEW_OPERATIONS_PERMISSION,
)
from trading_oms_backend.strategy_run_service import (
    DatasetRegistration,
    StrategyRunDraftRequest,
    StrategyRunError,
    StrategyRunService,
)
from trading_oms_backend.typed_strategy_simulation import NormalizedTrade, RiskContext
from trading_oms_backend.typed_workflow_definitions import (
    SqliteWorkflowDefinitionStore,
    WorkflowDefinitionError,
    WorkflowDefinitionSaveRequest,
)
from trading_oms_backend.typed_workflow_dsl import (
    WorkflowDslError,
    canonical_workflow_json,
    parse_workflow_dsl_document,
    workflow_node_catalog_payload,
)


def _guarded(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (sqlite3.Error, OSError, JournalError) as exc:
            raise HTTPException(
                status_code=503, detail="strategy run evidence unavailable"
            ) from exc

    return guarded


router = APIRouter()


class StrictApiBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorkflowDefinitionBody(StrictApiBody):
    workflow_id: str
    display_name: str
    description: str
    requested_at: str
    document: dict[str, Any]
    schema_version: Literal[2] = 2
    expected_version: int | None = None


class WorkflowValidationBody(StrictApiBody):
    document: dict[str, Any]


class DatasetTradeBody(StrictApiBody):
    timestamp: str
    price: str
    sequence: int
    source: str = "last_trade"


class DatasetRegistrationBody(StrictApiBody):
    dataset_id: str
    symbol: str
    contract_id: str
    primary_exchange: str
    currency: str
    routing: str
    min_tick: str = "0.01"
    session_date: str
    session_timezone: str
    rth_open: str
    rth_close: str
    source: str
    resolution: str
    complete: bool
    quality: str
    registered_at: str
    trades: list[DatasetTradeBody]


class StrategyRunDraftBody(StrictApiBody):
    run_id: str
    workflow_version: int
    symbol: str
    maximum_dollar_loss: str
    runtime_mode: str
    dataset_id: str
    expires_at: str
    requested_at: str


class StrategyRunArmBody(StrictApiBody):
    authorized_at: str
    expires_at: str


class StrategyRunDisarmBody(StrictApiBody):
    disarmed_at: str
    reason: str


class StrategyRunSimulationBody(StrictApiBody):
    buying_power: str
    concurrent_positions: int
    current_symbol_exposure: str
    daily_realized_loss: str
    reconciled: bool = False
    evaluated_at: str | None = None


@router.get("/api/typed-workflows/catalog")
@_guarded
def get_workflow_node_catalog(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_node_catalog",
        action="view",
    )
    return workflow_node_catalog_payload()


@router.get("/api/strategy-risk-policy")
@_guarded
def get_strategy_risk_policy(request: Request) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="risk_policy",
        action="view",
    )
    policy = get_strategy_run_service().current_risk_policy()
    return {
        "schema_version": 2,
        "version_id": policy.version_id,
        "max_dollar_risk": policy.max_dollar_risk,
        "max_shares": policy.max_shares,
        "max_notional": policy.max_notional,
        "max_concurrent_positions": policy.max_concurrent_positions,
        "max_symbol_exposure": policy.max_symbol_exposure,
        "max_daily_loss": policy.max_daily_loss,
        "admin_slippage_allowance": policy.admin_slippage_allowance,
        "chase_threshold": policy.chase_threshold,
        "max_data_age_seconds": policy.max_data_age_seconds,
        "mutable_through_run_request": False,
    }


@router.get("/api/typed-workflows")
@_guarded
def list_workflows(request: Request) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_definitions",
        action="view",
    )
    return [record.to_json_dict() for record in get_workflow_definition_store().list_workflows()]


@router.post("/api/typed-workflows")
@_guarded
def create_workflow(request: Request, definition: WorkflowDefinitionBody) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=AUTHOR_STRATEGY_PERMISSION,
        resource="workflow_definition",
        action="create",
    )
    try:
        request = _workflow_definition_request(definition)
        record = get_workflow_definition_store().create_workflow(request)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return record.to_json_dict()


@router.post("/api/typed-workflows/{workflow_id}/validate")
@_guarded
def validate_workflow(
    request: Request,
    workflow_id: str,
    validation: WorkflowValidationBody,
) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=AUTHOR_STRATEGY_PERMISSION,
        resource="workflow_definition",
        action="validate",
    )
    try:
        if validation.document.get("schema_version") != 2:
            raise WorkflowDslError("typed workflows require schema_version 2")
        document = parse_workflow_dsl_document(validation.document)
        document_workflow_id = document.workflow_id
        if document_workflow_id != workflow_id:
            raise WorkflowDslError("path workflow_id must match document workflow_id")
        canonical = canonical_workflow_json(validation.document)
    except WorkflowDslError as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return {
        "schema_version": validation.document.get("schema_version"),
        "workflow_id": workflow_id,
        "status": "valid",
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "errors": [],
    }


@router.get("/api/typed-workflows/{workflow_id}")
@_guarded
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
        raise HTTPException(status_code=_error_status(exc, missing=404), detail=str(exc)) from exc
    return record.to_json_dict()


@router.put("/api/typed-workflows/{workflow_id}")
@_guarded
def update_workflow(
    request: Request,
    workflow_id: str,
    definition: WorkflowDefinitionBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=AUTHOR_STRATEGY_PERMISSION,
        resource="workflow_definition",
        action="update",
    )
    try:
        request = _workflow_definition_request(definition)
        record = get_workflow_definition_store().update_workflow(workflow_id, request)
        get_strategy_run_service().disarm_runs_for_workflow_edit(
            workflow_id,
            current_version=record.version,
            disarmed_at=definition.requested_at,
            actor=identity.operator_id,
        )
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return record.to_json_dict()


@router.get("/api/typed-workflows/{workflow_id}/versions")
@_guarded
def list_workflow_versions(request: Request, workflow_id: str) -> list[dict[str, Any]]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="workflow_versions",
        action="view",
    )
    try:
        records = get_workflow_definition_store().list_workflow_versions(workflow_id)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=_error_status(exc, missing=404), detail=str(exc)) from exc
    return [record.to_json_dict() for record in records]


@router.post("/api/strategy-datasets")
@_guarded
def register_market_data_dataset(
    request: Request,
    dataset: DatasetRegistrationBody,
) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=OPERATE_STRATEGY_PERMISSION,
        resource="market_data_dataset",
        action="register",
    )
    try:
        record = get_strategy_run_service().register_dataset(
            _dataset_registration(dataset),
            tuple(
                NormalizedTrade(
                    timestamp=trade.timestamp,
                    price=trade.price,
                    sequence=trade.sequence,
                    source=trade.source,
                )
                for trade in dataset.trades
            ),
        )
    except (StrategyRunError, ValueError) as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return record.to_payload()


@router.get("/api/strategy-datasets/{dataset_id}")
@_guarded
def get_market_data_dataset(request: Request, dataset_id: str) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="market_data_dataset",
        action="view",
    )
    try:
        record = get_strategy_run_service().get_dataset(dataset_id)
    except StrategyRunError as exc:
        raise HTTPException(status_code=_error_status(exc, missing=404), detail=str(exc)) from exc
    return record.to_payload()


@router.post("/api/typed-workflows/{workflow_id}/runs")
@_guarded
def create_strategy_run(
    request: Request,
    workflow_id: str,
    draft: StrategyRunDraftBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=OPERATE_STRATEGY_PERMISSION,
        resource="strategy_run",
        action="draft",
    )
    try:
        record = get_strategy_run_service().create_draft(
            workflow_id,
            StrategyRunDraftRequest(
                run_id=draft.run_id,
                workflow_version=draft.workflow_version,
                symbol=draft.symbol,
                maximum_dollar_loss=draft.maximum_dollar_loss,
                runtime_mode=draft.runtime_mode,
                dataset_id=draft.dataset_id,
                expires_at=draft.expires_at,
                requested_at=draft.requested_at,
            ),
            requested_by=identity.operator_id,
        )
    except StrategyRunError as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return record.to_payload()


@router.post("/api/strategy-runs/{run_id}/arm")
@_guarded
def arm_strategy_run(
    request: Request,
    run_id: str,
    arm: StrategyRunArmBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=OPERATE_STRATEGY_PERMISSION,
        resource="strategy_run",
        action="arm",
    )
    try:
        get_emergency_stop_service().ensure_risk_increasing_allowed(
            resource=f"strategy_run.{run_id}",
            action="arm",
            checked_at=_utc_now(),
            actor=identity.operator_id,
        )
        record = get_strategy_run_service().arm_run(
            run_id,
            authorized_by=identity.operator_id,
            authorized_at=_utc_now(),
            expires_at=arm.expires_at,
        )
    except EmergencyStopError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except StrategyRunError as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return record.to_payload()


@router.post("/api/strategy-runs/{run_id}/disarm")
@_guarded
def disarm_strategy_run(
    request: Request,
    run_id: str,
    disarm: StrategyRunDisarmBody,
) -> dict[str, Any]:
    identity = _authorize_request(
        request,
        permission=OPERATE_STRATEGY_PERMISSION,
        resource="strategy_run",
        action="disarm",
    )
    try:
        record = get_strategy_run_service().disarm_run(
            run_id,
            disarmed_at=disarm.disarmed_at,
            actor=identity.operator_id,
            reason=disarm.reason,
        )
    except StrategyRunError as exc:
        raise HTTPException(status_code=_error_status(exc), detail=str(exc)) from exc
    return record.to_payload()


@router.post("/api/strategy-runs/{run_id}/simulate")
@_guarded
def simulate_strategy_run(
    request: Request,
    run_id: str,
    simulation: StrategyRunSimulationBody,
) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=OPERATE_STRATEGY_PERMISSION,
        resource="strategy_run",
        action="simulate",
    )
    try:
        record = get_strategy_run_service().simulate_run(
            run_id,
            risk_context=RiskContext(
                buying_power=simulation.buying_power,
                concurrent_positions=simulation.concurrent_positions,
                current_symbol_exposure=simulation.current_symbol_exposure,
                daily_realized_loss=simulation.daily_realized_loss,
            ),
            reconciled=simulation.reconciled,
            emergency_stop_active=get_emergency_stop_service().current_state().active,
            evaluated_at=_utc_now(),
        )
    except (StrategyRunError, ValueError) as exc:
        status_code = _error_status(exc)
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return record.to_payload()


@router.get("/api/strategy-runs/{run_id}")
@_guarded
def get_strategy_run(request: Request, run_id: str) -> dict[str, Any]:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="strategy_run",
        action="view",
    )
    try:
        record = get_strategy_run_service().get_run(run_id)
    except StrategyRunError as exc:
        raise HTTPException(status_code=_error_status(exc, missing=404), detail=str(exc)) from exc
    return record.to_payload()


@router.get("/api/strategy-runs/{run_id}/events")
@_guarded
def stream_strategy_run_events(request: Request, run_id: str) -> StreamingResponse:
    _authorize_request(
        request,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="strategy_run_events",
        action="view",
    )
    try:
        get_strategy_run_service().get_run(run_id)
    except StrategyRunError as exc:
        raise HTTPException(status_code=_error_status(exc, missing=404), detail=str(exc)) from exc
    events = [
        record.to_json_dict()
        for record in get_strategy_run_service().journal_records()
        if record.payload.get("run_id") == run_id
    ]

    def event_stream():
        for event in events:
            yield f"event: run-status\ndata: {json.dumps(event, sort_keys=True)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _workflow_definition_request(
    definition: WorkflowDefinitionBody,
) -> WorkflowDefinitionSaveRequest:
    return WorkflowDefinitionSaveRequest(
        expected_version=definition.expected_version,
        schema_version=definition.schema_version,
        workflow_id=definition.workflow_id,
        display_name=definition.display_name,
        description=definition.description,
        document=definition.document,
        requested_at=definition.requested_at,
    )


def _dataset_registration(dataset: DatasetRegistrationBody) -> DatasetRegistration:
    return DatasetRegistration(
        dataset_id=dataset.dataset_id,
        symbol=dataset.symbol,
        contract_id=dataset.contract_id,
        primary_exchange=dataset.primary_exchange,
        currency=dataset.currency,
        routing=dataset.routing,
        min_tick=dataset.min_tick,
        session_date=dataset.session_date,
        session_timezone=dataset.session_timezone,
        rth_open=dataset.rth_open,
        rth_close=dataset.rth_close,
        source=dataset.source,
        resolution=dataset.resolution,
        complete=dataset.complete,
        quality=dataset.quality,
        registered_at=dataset.registered_at,
    )


def _error_status(exc: Exception, *, missing: int = 400) -> int:
    message = str(exc)
    if "evidence unavailable" in message:
        return 503
    if "emergency stop" in message:
        return 423
    if "expected_version" in message:
        return 409
    return missing


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _state_root() -> Path:
    configured = os.environ.get("TRADING_OMS_TYPED_STATE_DIRECTORY")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / ".tmp" / "typed-strategy-state"


@lru_cache(maxsize=8)
def _services(root: Path):
    store = SqliteWorkflowDefinitionStore(root / "typed-strategy.sqlite3")
    service = StrategyRunService(
        store,
        database_path=root / "typed-strategy.sqlite3",
        dataset_directory=root / "datasets",
        journal=JsonlEventJournal(root / "strategy-run-journal.jsonl"),
    )
    return store, service


def get_workflow_definition_store() -> SqliteWorkflowDefinitionStore:
    return _services(_state_root())[0]


def get_strategy_run_service() -> StrategyRunService:
    return _services(_state_root())[1]


def _authorize_request(request: Request, **kwargs):
    from trading_oms_backend.app import _authorize_request as authorize

    return authorize(request, **kwargs)


def get_emergency_stop_service():
    from trading_oms_backend.app import get_emergency_stop_service as get_service

    return get_service()


def disarm_for_emergency(*, actor: str, timestamp: str, active: bool = True) -> None:
    if (_state_root() / "typed-strategy.sqlite3").exists():
        try:
            get_strategy_run_service().set_emergency_state(
                active=active,
                actor=actor,
                timestamp=timestamp,
            )
        except (StrategyRunError, sqlite3.Error, JournalError, OSError) as exc:
            raise EmergencyStopError(
                "typed strategy emergency state requires evidence recovery"
            ) from exc
