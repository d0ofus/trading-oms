from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from trading_oms_backend.event_journal import JournalError, JournalRecord, JsonlEventJournal
from trading_oms_backend.typed_strategy_simulation import (
    ArmAuthorization,
    BreakoutSimulationError,
    BreakoutSimulationResult,
    NormalizedTrade,
    RiskContext,
    RiskPolicy,
    RunEnvelope,
    fingerprint_run_envelope,
    simulate_first_five_minute_breakout,
)
from trading_oms_backend.typed_workflow_definitions import (
    SqliteWorkflowDefinitionStore,
    WorkflowDefinitionError,
)
from trading_oms_backend.typed_workflow_dsl import (
    WorkflowDslV2Document,
    parse_workflow_dsl_document,
)


class StrategyRunError(ValueError):
    """Raised when a strategy run or dataset transition would be unsafe."""


class StrategyEvidenceUnavailableError(StrategyRunError):
    """An incomplete or contradictory attempt cannot be replayed automatically."""


def _serialized(method):
    @wraps(method)
    def operation(self, *args, **kwargs):
        with self._journal.write_session():
            return method(self, *args, **kwargs)

    return operation


DEFAULT_RISK_POLICY = RiskPolicy(
    version_id="strategy-policy-001",
    max_dollar_risk="250.00",
    max_shares=1000,
    max_notional="50000.00",
    max_concurrent_positions=2,
    max_symbol_exposure="50000.00",
    max_daily_loss="500.00",
    admin_slippage_allowance="0.02",
    chase_threshold="0.50",
)


@dataclass(frozen=True)
class DatasetRegistration:
    dataset_id: str
    symbol: str
    contract_id: str
    primary_exchange: str
    currency: str
    routing: str
    session_date: str
    session_timezone: str
    rth_open: str
    rth_close: str
    source: str
    resolution: str
    complete: bool
    quality: str
    registered_at: str
    min_tick: str = "0.01"

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "contract_id", "primary_exchange"):
            _identifier(getattr(self, field_name), field_name)
        if (
            not isinstance(self.symbol, str)
            or not self.symbol
            or self.symbol != self.symbol.upper()
        ):
            raise StrategyRunError("symbol must be uppercase")
        if self.currency != "USD" or self.routing != "SMART":
            raise StrategyRunError("dataset must describe a SMART-routed USD stock")
        if self.session_timezone != "America/New_York":
            raise StrategyRunError("dataset session_timezone must be America/New_York")
        _parse_date(self.session_date, "session_date")
        _parse_time(self.rth_open, "rth_open")
        _parse_time(self.rth_close, "rth_close")
        if self.source not in {"local_fixture", "paper_market_data", "live_forward_capture"}:
            raise StrategyRunError("dataset source is unsupported")
        if self.resolution not in {"trade_ticks", "five_second_bars"}:
            raise StrategyRunError("dataset resolution is unsupported")
        if not isinstance(self.complete, bool):
            raise StrategyRunError("dataset complete must be boolean")
        if self.quality not in {"complete", "gap_detected", "out_of_order", "degraded"}:
            raise StrategyRunError("dataset quality is unsupported")
        if self.complete and self.quality not in {"complete", "degraded"}:
            raise StrategyRunError("complete dataset must have complete or degraded quality")
        _parse_timestamp(self.registered_at, "registered_at")
        _positive_decimal_string(self.min_tick, "min_tick")


@dataclass(frozen=True)
class DatasetRecord:
    registration: DatasetRegistration
    checksum: str
    manifest_checksum: str
    trade_count: int
    start_at: str
    end_at: str

    @property
    def dataset_id(self) -> str:
        return self.registration.dataset_id

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "dataset_id": self.registration.dataset_id,
            "symbol": self.registration.symbol,
            "contract": {
                "contract_id": self.registration.contract_id,
                "primary_exchange": self.registration.primary_exchange,
                "currency": self.registration.currency,
                "routing": self.registration.routing,
                "min_tick": self.registration.min_tick,
            },
            "session": {
                "date": self.registration.session_date,
                "timezone": self.registration.session_timezone,
                "rth_open": self.registration.rth_open,
                "rth_close": self.registration.rth_close,
            },
            "source": self.registration.source,
            "resolution": self.registration.resolution,
            "complete": self.registration.complete,
            "quality": self.registration.quality,
            "registered_at": self.registration.registered_at,
            "checksum": self.checksum,
            "manifest_checksum": self.manifest_checksum,
            "trade_count": self.trade_count,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "simulated_data_only": True,
        }


@dataclass(frozen=True)
class StrategyRunDraftRequest:
    run_id: str
    workflow_version: int
    symbol: str
    maximum_dollar_loss: str
    runtime_mode: str
    dataset_id: str
    expires_at: str
    requested_at: str

    def __post_init__(self) -> None:
        _identifier(self.run_id, "run_id")
        _identifier(self.dataset_id, "dataset_id")
        if (
            isinstance(self.workflow_version, bool)
            or not isinstance(self.workflow_version, int)
            or self.workflow_version < 1
        ):
            raise StrategyRunError("workflow_version must be positive")
        if (
            not isinstance(self.symbol, str)
            or not self.symbol
            or self.symbol != self.symbol.upper()
        ):
            raise StrategyRunError("symbol must be uppercase")
        _positive_decimal_string(self.maximum_dollar_loss, "maximum_dollar_loss")
        if self.runtime_mode not in {"historical_simulation", "live_simulation"}:
            raise StrategyRunError("runtime_mode must be a supported simulation mode")
        requested_at = _parse_timestamp(self.requested_at, "requested_at")
        expires_at = _parse_timestamp(self.expires_at, "expires_at")
        if expires_at <= requested_at:
            raise StrategyRunError("expires_at must be after requested_at")


@dataclass(frozen=True)
class StrategyRunRecord:
    run_id: str
    state: str
    envelope: RunEnvelope
    fingerprint: str
    requested_by: str
    created_at: str
    updated_at: str
    authorization: ArmAuthorization | None = None
    result: BreakoutSimulationResult | None = None
    disarm_reason: str | None = None
    journal_references: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "state": self.state,
            "fingerprint": self.fingerprint,
            "envelope": self.envelope.to_payload(),
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "authorization": (
                None if self.authorization is None else _authorization_payload(self.authorization)
            ),
            "result": None if self.result is None else self.result.to_payload(),
            "disarm_reason": self.disarm_reason,
            "journal_references": list(self.journal_references),
            "execution_target": "fake_broker",
            "simulated": True,
        }


class StrategyRunService:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS strategy_schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at TEXT NOT NULL,
      description TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategy_run_evidence (
      run_id TEXT PRIMARY KEY,
      record_sha256 TEXT NOT NULL,
      manifest_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategy_emergency_state (
      singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
      active INTEGER NOT NULL CHECK (active IN (0, 1))
    );
    INSERT OR IGNORE INTO strategy_emergency_state (singleton, active) VALUES (1, 0);

    CREATE TABLE IF NOT EXISTS market_data_datasets (
      dataset_id TEXT PRIMARY KEY,
      checksum TEXT NOT NULL,
      registered_at TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS risk_policy_versions (
      version_id TEXT PRIMARY KEY,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategy_runs (
      run_id TEXT PRIMARY KEY,
      workflow_id TEXT NOT NULL,
      workflow_version INTEGER NOT NULL,
      state TEXT NOT NULL,
      fingerprint TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_strategy_runs_workflow
      ON strategy_runs (workflow_id, workflow_version, state);

    CREATE TABLE IF NOT EXISTS run_authorizations (
      run_id TEXT PRIMARY KEY,
      fingerprint TEXT NOT NULL,
      authorized_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS simulation_reports (
      run_id TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategy_orders (
      order_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategy_fills (
      fill_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategy_positions (
      run_id TEXT PRIMARY KEY,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS protection_state (
      run_id TEXT PRIMARY KEY,
      state TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS reconciliation_results (
      reconciliation_id TEXT PRIMARY KEY,
      run_id TEXT,
      state TEXT NOT NULL,
      payload_json TEXT NOT NULL
    );
    """

    def __init__(
        self,
        workflow_store: SqliteWorkflowDefinitionStore,
        *,
        database_path: str | Path,
        dataset_directory: str | Path,
        journal: JsonlEventJournal,
        clock: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(workflow_store, SqliteWorkflowDefinitionStore):
            raise StrategyRunError("workflow_store must be SqliteWorkflowDefinitionStore")
        if not isinstance(journal, JsonlEventJournal):
            raise StrategyRunError("journal must be JsonlEventJournal")
        self._workflow_store = workflow_store
        self._database_path = Path(database_path)
        self._dataset_directory = Path(dataset_directory)
        self._journal = journal
        self._clock = clock or (lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        self._initialize()

    @_serialized
    def register_dataset(
        self,
        registration: DatasetRegistration,
        trades: Iterable[NormalizedTrade],
    ) -> DatasetRecord:
        if not isinstance(registration, DatasetRegistration):
            raise StrategyRunError("registration must be DatasetRegistration")
        trade_values = tuple(trades)
        if not trade_values or any(not isinstance(item, NormalizedTrade) for item in trade_values):
            raise StrategyRunError("dataset must contain normalized trades")
        lines = tuple(_trade_line(item) for item in trade_values)
        checksum = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
        manifest_checksum = hashlib.sha256(
            _stable_json(
                {
                    "registration": _dataset_registration_payload(registration),
                    "data_checksum": checksum,
                    "trade_count": len(trade_values),
                    "start_at": trade_values[0].timestamp,
                    "end_at": trade_values[-1].timestamp,
                }
            ).encode("utf-8")
        ).hexdigest()
        record = DatasetRecord(
            registration=registration,
            checksum=checksum,
            manifest_checksum=manifest_checksum,
            trade_count=len(trade_values),
            start_at=trade_values[0].timestamp,
            end_at=trade_values[-1].timestamp,
        )
        existing = self._optional_dataset(registration.dataset_id)
        if existing is not None:
            if existing == record:
                return existing
            raise StrategyRunError("dataset_id is immutable and already has different content")

        dataset_path = self._dataset_path(registration.dataset_id)
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = dataset_path.with_suffix(".jsonl.tmp")
        with temporary_path.open("x", encoding="utf-8", newline="\n") as dataset_file:
            dataset_file.writelines(lines)
        temporary_path.replace(dataset_path)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_data_datasets (
                  dataset_id, checksum, registered_at, payload_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    record.dataset_id,
                    record.checksum,
                    registration.registered_at,
                    _stable_json(record.to_payload()),
                ),
            )
        self._journal.append(
            "market_data.dataset.registered",
            {
                "schema_version": 2,
                "dataset_id": record.dataset_id,
                "symbol": registration.symbol,
                "checksum": record.checksum,
                "manifest_checksum": record.manifest_checksum,
                "complete": registration.complete,
                "quality": registration.quality,
                "resolution": registration.resolution,
            },
            timestamp=registration.registered_at,
        )
        return record

    def get_dataset(self, dataset_id: str) -> DatasetRecord:
        _identifier(dataset_id, "dataset_id")
        record = self._optional_dataset(dataset_id)
        if record is None:
            raise StrategyRunError("unknown dataset_id")
        return record

    @_serialized
    def create_draft(
        self,
        workflow_id: str,
        request: StrategyRunDraftRequest,
        *,
        requested_by: str,
    ) -> StrategyRunRecord:
        _identifier(requested_by, "requested_by")
        try:
            workflow = self._workflow_store.get_workflow_version(
                workflow_id,
                request.workflow_version,
            )
        except WorkflowDefinitionError as exc:
            raise StrategyRunError(str(exc)) from exc
        if workflow.schema_version != 2 or workflow.checksum is None:
            raise StrategyRunError("new strategy runs require a schema-v2 workflow version")
        parsed = parse_workflow_dsl_document(workflow.document)
        if not isinstance(parsed, WorkflowDslV2Document):
            raise StrategyRunError("new strategy runs require a schema-v2 workflow")
        if request.runtime_mode not in parsed.runtime_modes:
            raise StrategyRunError("runtime_mode is not enabled by the workflow version")
        dataset = self.get_dataset(request.dataset_id)
        registration = dataset.registration
        if not registration.complete or registration.quality not in {"complete", "degraded"}:
            raise StrategyRunError("dataset must be complete before a run can be drafted")
        if registration.resolution == "five_second_bars":
            raise StrategyRunError(
                "five_second_bars require a pessimistic bar-ordering engine that is not yet enabled"
            )
        if (
            _single_node_config(parsed, "historical_dataset")["resolution"]
            != registration.resolution
        ):
            raise StrategyRunError("dataset resolution must match the workflow source")
        if registration.quality != "complete":
            raise StrategyRunError("degraded datasets cannot create an executable run")
        if registration.symbol != request.symbol:
            raise StrategyRunError("runtime symbol must match the immutable dataset contract")
        if (
            request.runtime_mode == "historical_simulation"
            and registration.source == "live_forward_capture"
        ):
            raise StrategyRunError("historical_simulation requires an immutable historical dataset")
        if (
            request.runtime_mode == "live_simulation"
            and registration.source != "live_forward_capture"
        ):
            raise StrategyRunError("live_simulation requires a live-forward capture dataset")

        entry_lifetime = _single_node_config(parsed, "entry_lifetime")["value"]
        position_lifetime = _single_node_config(parsed, "position_lifetime")
        if position_lifetime.get("kind") == "exit_on_typed_condition":
            raise StrategyRunError(
                "exit_on_typed_condition requires a compiled typed-exit runtime "
                "that is not yet enabled"
            )
        opening_range_minutes = _single_node_config(parsed, "opening_range_high")["minutes"]
        policy = self.current_risk_policy()
        envelope = RunEnvelope(
            run_id=request.run_id,
            workflow_id=workflow.workflow_id,
            workflow_version=workflow.version,
            workflow_checksum=workflow.checksum,
            symbol=request.symbol,
            contract_id=registration.contract_id,
            primary_exchange=registration.primary_exchange,
            currency=registration.currency,
            routing=registration.routing,
            min_tick=registration.min_tick,
            maximum_dollar_loss=request.maximum_dollar_loss,
            runtime_mode=request.runtime_mode,
            dataset_id=registration.dataset_id,
            session_date=registration.session_date,
            session_timezone=registration.session_timezone,
            rth_open=registration.rth_open,
            rth_close=registration.rth_close,
            entry_lifetime=str(entry_lifetime),
            position_lifetime=position_lifetime,
            risk_policy_version=policy.version_id,
            expires_at=request.expires_at,
            opening_range_minutes=int(opening_range_minutes),
            dataset_resolution=registration.resolution,
        )
        fingerprint = fingerprint_run_envelope(envelope)
        existing = self._optional_run(request.run_id)
        if existing is not None:
            if existing.state == "draft" and existing.fingerprint == fingerprint:
                return existing
            raise StrategyRunError("run_id is immutable and already exists")
        journal_record = self._journal.append(
            "workflow.run.drafted",
            {
                "schema_version": 2,
                "run_id": request.run_id,
                "workflow_id": workflow.workflow_id,
                "workflow_version": workflow.version,
                "symbol": request.symbol,
                "runtime_mode": request.runtime_mode,
                "fingerprint": fingerprint,
                "requested_by": requested_by,
                "execution_target": "fake_broker",
            },
            timestamp=request.requested_at,
        )
        record = StrategyRunRecord(
            run_id=request.run_id,
            state="draft",
            envelope=envelope,
            fingerprint=fingerprint,
            requested_by=requested_by,
            created_at=request.requested_at,
            updated_at=request.requested_at,
            journal_references=(_journal_reference(journal_record),),
        )
        self._put_run(record)
        return record

    @_serialized
    def arm_run(
        self,
        run_id: str,
        *,
        authorized_by: str,
        authorized_at: str,
        expires_at: str,
    ) -> StrategyRunRecord:
        _identifier(authorized_by, "authorized_by")
        self._ensure_emergency_allowed()
        record = self.get_run(run_id)
        latest = self._workflow_store.get_workflow(record.envelope.workflow_id)
        if latest.version != record.envelope.workflow_version:
            raise StrategyRunError("workflow version changed; create a new draft")
        if record.state != "draft":
            raise StrategyRunError("only a draft run can be armed")
        if fingerprint_run_envelope(record.envelope) != record.fingerprint:
            raise StrategyRunError("draft fingerprint no longer matches its envelope")
        authorization = ArmAuthorization(
            run_id=run_id,
            fingerprint=record.fingerprint,
            authorized_at=authorized_at,
            expires_at=expires_at,
            authorized_by=authorized_by,
        )
        if _parse_timestamp(expires_at, "expires_at") > _parse_timestamp(
            record.envelope.expires_at,
            "run expires_at",
        ):
            raise StrategyRunError("authorization expiry must be within the draft envelope")
        journal_record = self._journal.append(
            "workflow.run.armed",
            {
                "schema_version": 2,
                "run_id": run_id,
                "workflow_id": record.envelope.workflow_id,
                "workflow_version": record.envelope.workflow_version,
                "symbol": record.envelope.symbol,
                "fingerprint": record.fingerprint,
                "expires_at": expires_at,
                "authorized_by": authorized_by,
                "execution_target": "fake_broker",
            },
            timestamp=authorized_at,
        )
        armed = StrategyRunRecord(
            run_id=record.run_id,
            state="armed",
            envelope=record.envelope,
            fingerprint=record.fingerprint,
            requested_by=record.requested_by,
            created_at=record.created_at,
            updated_at=authorized_at,
            authorization=authorization,
            journal_references=record.journal_references + (_journal_reference(journal_record),),
        )
        self._put_authorization(authorization)
        self._put_run(armed)
        return armed

    @_serialized
    def disarm_run(
        self,
        run_id: str,
        *,
        disarmed_at: str,
        actor: str,
        reason: str,
    ) -> StrategyRunRecord:
        _identifier(actor, "actor")
        _identifier(reason, "reason")
        record = self.get_run(run_id)
        if record.state in {"completed", "blocked", "disarmed"}:
            if record.state == "disarmed" and record.disarm_reason == reason:
                return record
            raise StrategyRunError("run can no longer be disarmed")
        journal_record = self._journal.append(
            "workflow.run.disarmed",
            {
                "schema_version": 2,
                "run_id": record.run_id,
                "workflow_id": record.envelope.workflow_id,
                "workflow_version": record.envelope.workflow_version,
                "symbol": record.envelope.symbol,
                "reason": reason,
                "actor": actor,
            },
            timestamp=disarmed_at,
        )
        disarmed = StrategyRunRecord(
            run_id=record.run_id,
            state="disarmed",
            envelope=record.envelope,
            fingerprint=record.fingerprint,
            requested_by=record.requested_by,
            created_at=record.created_at,
            updated_at=disarmed_at,
            authorization=record.authorization,
            disarm_reason=reason,
            journal_references=record.journal_references + (_journal_reference(journal_record),),
        )
        self._put_run(disarmed)
        return disarmed

    def disarm_runs_for_workflow_edit(
        self,
        workflow_id: str,
        *,
        current_version: int,
        disarmed_at: str,
        actor: str,
    ) -> int:
        count = 0
        for record in self._runs_for_workflow(workflow_id):
            if record.envelope.workflow_version != current_version and record.state in {
                "draft",
                "armed",
            }:
                self.disarm_run(
                    record.run_id,
                    disarmed_at=disarmed_at,
                    actor=actor,
                    reason="workflow_version_changed",
                )
                count += 1
        return count

    def disarm_all_active(
        self,
        *,
        disarmed_at: str,
        actor: str,
        reason: str,
    ) -> int:
        count = 0
        for record in self._active_runs():
            self.disarm_run(
                record.run_id,
                disarmed_at=disarmed_at,
                actor=actor,
                reason=reason,
            )
            count += 1
        return count

    @_serialized
    def simulate_run(
        self,
        run_id: str,
        *,
        risk_context: RiskContext,
        reconciled: bool = True,
        emergency_stop_active: bool = False,
        evaluated_at: str | None = None,
    ) -> StrategyRunRecord:
        record = self.get_run(run_id)
        execution_request = {
            "risk_context": asdict(risk_context),
            "reconciled": reconciled,
            "emergency_stop_active": emergency_stop_active,
        }
        if record.state == "completed" and record.result is not None:
            reservations = [
                event
                for event in self._journal.read_all()
                if event.event_type == "workflow.run.execution_reserved"
                and event.payload.get("run_id") == run_id
            ]
            if len(reservations) != 1:
                raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
            if reservations[0].payload.get("execution_request") != execution_request:
                raise StrategyRunError("execution request differs from the completed attempt")
            return record
        if record.state != "armed" or record.authorization is None:
            raise StrategyRunError("run must be armed before simulation")
        latest = self._workflow_store.get_workflow(record.envelope.workflow_id)
        if latest.version != record.envelope.workflow_version:
            raise StrategyRunError("workflow version changed; create a new draft")
        dataset = self.get_dataset(record.envelope.dataset_id)
        trades = self._load_trades(dataset)
        effective_evaluated_at = evaluated_at or self._clock()
        self._reserve_execution(record)
        reserved = self._journal.append(
            "workflow.run.execution_reserved",
            {
                "schema_version": 2,
                "run_id": run_id,
                "fingerprint": record.fingerprint,
                "execution_request": execution_request,
            },
            timestamp=effective_evaluated_at,
        )
        record = replace(
            record, journal_references=record.journal_references + (_journal_reference(reserved),)
        )
        try:
            result = simulate_first_five_minute_breakout(
                trades=trades,
                envelope=record.envelope,
                authorization=record.authorization,
                policy=self.current_risk_policy(),
                risk_context=risk_context,
                data_complete=dataset.registration.complete,
                data_quality=(
                    "complete"
                    if dataset.registration.quality == "degraded"
                    else dataset.registration.quality
                ),
                reconciled=reconciled,
                emergency_stop_active=emergency_stop_active,
                evaluated_at=effective_evaluated_at,
            )
        except BreakoutSimulationError as exc:
            references = list(record.journal_references)
            for event in exc.audit_events:
                partial_record = self._journal.append(
                    str(event["event_type"]),
                    {
                        "schema_version": 2,
                        "run_id": record.run_id,
                        "workflow_id": record.envelope.workflow_id,
                        "symbol": record.envelope.symbol,
                        **dict(event["payload"]),
                    },
                    timestamp=str(event["timestamp"]),
                )
                references.append(_journal_reference(partial_record))
            if _is_risk_failure(str(exc)) and not any(
                event["event_type"] == "workflow.risk.blocked" for event in exc.audit_events
            ):
                risk_record = self._journal.append(
                    "workflow.risk.blocked",
                    {
                        "schema_version": 2,
                        "run_id": record.run_id,
                        "workflow_id": record.envelope.workflow_id,
                        "symbol": record.envelope.symbol,
                        "policy_version": record.envelope.risk_policy_version,
                        "reason": str(exc),
                    },
                    timestamp=effective_evaluated_at,
                )
                references.append(_journal_reference(risk_record))
            journal_record = self._journal.append(
                "workflow.run.blocked",
                {
                    "schema_version": 2,
                    "run_id": record.run_id,
                    "workflow_id": record.envelope.workflow_id,
                    "symbol": record.envelope.symbol,
                    "reason": str(exc),
                },
                timestamp=effective_evaluated_at,
            )
            blocked = StrategyRunRecord(
                run_id=record.run_id,
                state="blocked",
                envelope=record.envelope,
                fingerprint=record.fingerprint,
                requested_by=record.requested_by,
                created_at=record.created_at,
                updated_at=effective_evaluated_at,
                authorization=record.authorization,
                disarm_reason=str(exc),
                journal_references=tuple(references) + (_journal_reference(journal_record),),
            )
            self._put_run(blocked)
            raise StrategyRunError(str(exc)) from exc

        references = list(record.journal_references)
        for event in result.audit_events:
            event_record = self._journal.append(
                str(event["event_type"]),
                {
                    "schema_version": 2,
                    "run_id": record.run_id,
                    "workflow_id": record.envelope.workflow_id,
                    "symbol": record.envelope.symbol,
                    **dict(event["payload"]),
                },
                timestamp=str(event["timestamp"]),
            )
            references.append(_journal_reference(event_record))
        completion_timestamp = (
            result.audit_events[-1]["timestamp"] if result.audit_events else effective_evaluated_at
        )
        completion_record = self._journal.append(
            "workflow.run.completed",
            {
                "schema_version": 2,
                "run_id": record.run_id,
                "workflow_id": record.envelope.workflow_id,
                "symbol": record.envelope.symbol,
                "status": result.status,
                "simulated": True,
            },
            timestamp=str(completion_timestamp),
        )
        references.append(_journal_reference(completion_record))
        completed = StrategyRunRecord(
            run_id=record.run_id,
            state="completed",
            envelope=record.envelope,
            fingerprint=record.fingerprint,
            requested_by=record.requested_by,
            created_at=record.created_at,
            updated_at=str(completion_timestamp),
            authorization=record.authorization,
            result=result,
            journal_references=tuple(references),
        )
        self._put_report(result)
        self._persist_execution_artifacts(completed)
        self._put_run(completed)
        return completed

    @_serialized
    def get_run(self, run_id: str) -> StrategyRunRecord:
        _identifier(run_id, "run_id")
        record = self._optional_run(run_id)
        if record is None:
            raise StrategyRunError("unknown run_id")
        return record

    def _reserve_execution(self, record: StrategyRunRecord) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            emergency = connection.execute(
                "SELECT active FROM strategy_emergency_state WHERE singleton = 1"
            ).fetchone()
            if emergency is None or emergency["active"] != 0:
                raise StrategyRunError("emergency stop is active or unknown")
            pending = connection.execute(
                "SELECT 1 FROM strategy_runs WHERE state = 'executing' LIMIT 1"
            ).fetchone()
            if pending is not None:
                raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
            updated = connection.execute(
                "UPDATE strategy_runs SET state = 'executing' "
                "WHERE run_id = ? AND state = 'armed' AND payload_json = ?",
                (record.run_id, _stable_json(record.to_payload())),
            )
            if updated.rowcount != 1:
                raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")

    def _ensure_emergency_allowed(self) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT active FROM strategy_emergency_state WHERE singleton = 1"
            ).fetchone()
        if row is None or row["active"] != 0:
            raise StrategyRunError("emergency stop is active or unknown")

    @_serialized
    def set_emergency_state(self, *, active: bool, actor: str, timestamp: str) -> None:
        _identifier(actor, "actor")
        _parse_timestamp(timestamp, "emergency timestamp")
        if active:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE strategy_emergency_state SET active = 1 WHERE singleton = 1"
                )
        self._journal.append(
            "workflow.emergency.activated" if active else "workflow.emergency.clear_requested",
            {"schema_version": 2, "actor": actor, "active": active},
            timestamp=timestamp,
        )
        # Clearing must not revive a prior authorization, including after a restart.
        self.disarm_all_active(
            disarmed_at=timestamp, actor=actor, reason="emergency_stop_activated"
        )
        if not active:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE strategy_emergency_state SET active = 0 WHERE singleton = 1"
                )

    def _manifest(self, record: StrategyRunRecord) -> list[dict[str, Any]]:
        try:
            records = self._journal.read_all()
            relevant = [r for r in records if r.payload.get("run_id") == record.run_id]
            if tuple(_journal_reference(r) for r in relevant) != record.journal_references:
                raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
            if not relevant or fingerprint_run_envelope(record.envelope) != record.fingerprint:
                raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
            return [
                {
                    "sequence": r.sequence,
                    "sha256": hashlib.sha256(r.to_json_line().encode("utf-8")).hexdigest(),
                }
                for r in relevant
            ]
        except (JournalError, OSError, ValueError) as exc:
            raise StrategyEvidenceUnavailableError("strategy run evidence unavailable") from exc

    def _validate_run_evidence(self, record: StrategyRunRecord) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_sha256, manifest_json FROM strategy_run_evidence WHERE run_id = ?",
                (record.run_id,),
            ).fetchone()
        digest = hashlib.sha256(_stable_json(record.to_payload()).encode("utf-8")).hexdigest()
        if row is None or row["record_sha256"] != digest:
            raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
        try:
            expected = json.loads(row["manifest_json"])
        except (TypeError, ValueError) as exc:
            raise StrategyEvidenceUnavailableError("strategy run evidence unavailable") from exc
        if expected != self._manifest(record):
            raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")

    def current_risk_policy(self) -> RiskPolicy:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM risk_policy_versions WHERE version_id = ?",
                (DEFAULT_RISK_POLICY.version_id,),
            ).fetchone()
        if row is None:
            raise StrategyRunError("administrator risk policy is unavailable")
        return _risk_policy_from_payload(_json_object(str(row["payload_json"]), "risk policy"))

    def journal_records(self) -> tuple[JournalRecord, ...]:
        return tuple(self._journal.read_all())

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._dataset_directory.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(self._SCHEMA)
            connection.execute(
                """
                INSERT OR IGNORE INTO strategy_schema_migrations (
                  version, applied_at, description
                )
                VALUES (1, '2026-08-25T00:00:00Z', 'workflow-dsl-v2-foundation')
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO risk_policy_versions (version_id, payload_json)
                VALUES (?, ?)
                """,
                (
                    DEFAULT_RISK_POLICY.version_id,
                    _stable_json(_risk_policy_payload(DEFAULT_RISK_POLICY)),
                ),
            )

    def _optional_dataset(self, dataset_id: str) -> DatasetRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM market_data_datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
        return (
            None
            if row is None
            else _dataset_from_payload(_json_object(str(row["payload_json"]), "dataset"))
        )

    def _optional_run(self, run_id: str) -> StrategyRunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state, fingerprint, payload_json FROM strategy_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        if row["state"] == "executing":
            raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
        try:
            record = _run_from_payload(_json_object(str(row["payload_json"]), "strategy run"))
            if record.state != row["state"] or record.fingerprint != row["fingerprint"]:
                raise StrategyEvidenceUnavailableError("strategy run evidence unavailable")
            self._validate_run_evidence(record)
            return record
        except (KeyError, TypeError, ValueError) as exc:
            raise StrategyEvidenceUnavailableError("strategy run evidence unavailable") from exc

    def _runs_for_workflow(self, workflow_id: str) -> tuple[StrategyRunRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_runs
                WHERE workflow_id = ?
                ORDER BY updated_at, run_id
                """,
                (workflow_id,),
            ).fetchall()
        return tuple(
            _run_from_payload(_json_object(str(row["payload_json"]), "strategy run"))
            for row in rows
        )

    def _active_runs(self) -> tuple[StrategyRunRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_runs
                WHERE state IN ('draft', 'armed')
                ORDER BY updated_at, run_id
                """
            ).fetchall()
        return tuple(
            _run_from_payload(_json_object(str(row["payload_json"]), "strategy run"))
            for row in rows
        )

    def _put_run(self, record: StrategyRunRecord) -> None:
        manifest = self._manifest(record)
        digest = hashlib.sha256(_stable_json(record.to_payload()).encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO strategy_runs (
                  run_id, workflow_id, workflow_version, state,
                  fingerprint, updated_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  state = excluded.state,
                  fingerprint = excluded.fingerprint,
                  updated_at = excluded.updated_at,
                  payload_json = excluded.payload_json
                """,
                (
                    record.run_id,
                    record.envelope.workflow_id,
                    record.envelope.workflow_version,
                    record.state,
                    record.fingerprint,
                    record.updated_at,
                    _stable_json(record.to_payload()),
                ),
            )
            connection.execute(
                "INSERT INTO strategy_run_evidence (run_id, record_sha256, manifest_json) "
                "VALUES (?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET "
                "record_sha256 = excluded.record_sha256, manifest_json = excluded.manifest_json",
                (record.run_id, digest, json.dumps(manifest, sort_keys=True)),
            )

    def _put_authorization(self, authorization: ArmAuthorization) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_authorizations (
                  run_id, fingerprint, authorized_at, expires_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    authorization.run_id,
                    authorization.fingerprint,
                    authorization.authorized_at,
                    authorization.expires_at,
                    _stable_json(_authorization_payload(authorization)),
                ),
            )

    def _put_report(self, result: BreakoutSimulationResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO simulation_reports (run_id, status, payload_json)
                VALUES (?, ?, ?)
                """,
                (result.run_id, result.status, _stable_json(result.to_payload())),
            )

    def _persist_execution_artifacts(self, record: StrategyRunRecord) -> None:
        result = record.result
        if result is None or result.idempotency_key is None:
            return
        order_payload = {
            "schema_version": 2,
            "run_id": record.run_id,
            "order_id": result.idempotency_key,
            "entry_type": "stop_market",
            "shares": result.shares,
            "protective_stop_price": result.protective_stop_price,
            "status": result.status,
            "execution_target": "fake_broker",
            "simulated": True,
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO strategy_orders (order_id, run_id, payload_json) VALUES (?, ?, ?)",
                (result.idempotency_key, record.run_id, _stable_json(order_payload)),
            )
            fill_prices = [result.entry_fill_price, result.exit_fill_price]
            for index, fill_price in enumerate(fill_prices, start=1):
                if fill_price is None:
                    continue
                fill_id = f"{result.idempotency_key}-fill-{index}"
                connection.execute(
                    "INSERT INTO strategy_fills (fill_id, run_id, payload_json) VALUES (?, ?, ?)",
                    (
                        fill_id,
                        record.run_id,
                        _stable_json(
                            {
                                "schema_version": 2,
                                "run_id": record.run_id,
                                "fill_id": fill_id,
                                "price": fill_price,
                                "shares": result.shares,
                                "simulated": True,
                            }
                        ),
                    ),
                )
            if result.entry_fill_price is not None:
                connection.execute(
                    "INSERT INTO strategy_positions (run_id, payload_json) VALUES (?, ?)",
                    (
                        record.run_id,
                        _stable_json(
                            {
                                "schema_version": 2,
                                "run_id": record.run_id,
                                "state": result.status,
                                "shares": result.shares,
                                "realized_pnl": result.realized_pnl,
                                "simulated": True,
                            }
                        ),
                    ),
                )
            connection.execute(
                """
                INSERT INTO protection_state (run_id, state, payload_json)
                VALUES (?, ?, ?)
                """,
                (
                    record.run_id,
                    result.protection_state,
                    _stable_json(
                        {
                            "schema_version": 2,
                            "run_id": record.run_id,
                            "state": result.protection_state,
                            "protective_stop_price": result.protective_stop_price,
                        }
                    ),
                ),
            )

    def _load_trades(self, dataset: DatasetRecord) -> tuple[NormalizedTrade, ...]:
        dataset_path = self._dataset_path(dataset.dataset_id)
        if not dataset_path.exists():
            raise StrategyRunError("dataset file is missing")
        raw_bytes = dataset_path.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != dataset.checksum:
            raise StrategyRunError("dataset checksum mismatch")
        trades: list[NormalizedTrade] = []
        for line_number, line in enumerate(raw_bytes.decode("utf-8").splitlines(), start=1):
            payload = _json_object(line, f"dataset line {line_number}")
            trades.append(
                NormalizedTrade(
                    timestamp=payload["timestamp"],
                    price=payload["price"],
                    sequence=payload["sequence"],
                    source=payload["source"],
                )
            )
        return tuple(trades)

    def _dataset_path(self, dataset_id: str) -> Path:
        _identifier(dataset_id, "dataset_id")
        path = (self._dataset_directory / f"{dataset_id}.jsonl").resolve()
        directory = self._dataset_directory.resolve()
        if path.parent != directory:
            raise StrategyRunError("dataset path must remain inside the dataset directory")
        return path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _single_node_config(document: WorkflowDslV2Document, node_type: str) -> dict[str, Any]:
    configs = [dict(node.config) for node in document.nodes if node.type == node_type]
    if len(configs) != 1:
        raise StrategyRunError(f"workflow must contain exactly one {node_type} node")
    return configs[0]


def _trade_line(trade: NormalizedTrade) -> str:
    return (
        _stable_json(
            {
                "schema_version": 2,
                "timestamp": trade.timestamp,
                "price": trade.price,
                "sequence": trade.sequence,
                "source": trade.source,
            }
        )
        + "\n"
    )


def _dataset_from_payload(payload: Mapping[str, Any]) -> DatasetRecord:
    contract = _mapping(payload.get("contract"), "dataset contract")
    session = _mapping(payload.get("session"), "dataset session")
    registration = DatasetRegistration(
        dataset_id=payload["dataset_id"],
        symbol=payload["symbol"],
        contract_id=contract["contract_id"],
        primary_exchange=contract["primary_exchange"],
        currency=contract["currency"],
        routing=contract["routing"],
        min_tick=contract["min_tick"],
        session_date=session["date"],
        session_timezone=session["timezone"],
        rth_open=session["rth_open"],
        rth_close=session["rth_close"],
        source=payload["source"],
        resolution=payload["resolution"],
        complete=payload["complete"],
        quality=payload["quality"],
        registered_at=payload["registered_at"],
    )
    return DatasetRecord(
        registration=registration,
        checksum=payload["checksum"],
        manifest_checksum=payload.get("manifest_checksum", payload["checksum"]),
        trade_count=payload["trade_count"],
        start_at=payload["start_at"],
        end_at=payload["end_at"],
    )


def _dataset_registration_payload(registration: DatasetRegistration) -> dict[str, Any]:
    return {
        "dataset_id": registration.dataset_id,
        "symbol": registration.symbol,
        "contract_id": registration.contract_id,
        "primary_exchange": registration.primary_exchange,
        "currency": registration.currency,
        "routing": registration.routing,
        "min_tick": registration.min_tick,
        "session_date": registration.session_date,
        "session_timezone": registration.session_timezone,
        "rth_open": registration.rth_open,
        "rth_close": registration.rth_close,
        "source": registration.source,
        "resolution": registration.resolution,
        "complete": registration.complete,
        "quality": registration.quality,
        "registered_at": registration.registered_at,
    }


def _run_from_payload(payload: Mapping[str, Any]) -> StrategyRunRecord:
    authorization_payload = payload.get("authorization")
    result_payload = payload.get("result")
    return StrategyRunRecord(
        run_id=payload["run_id"],
        state=payload["state"],
        envelope=RunEnvelope.from_payload(_mapping(payload.get("envelope"), "run envelope")),
        fingerprint=payload["fingerprint"],
        requested_by=payload["requested_by"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        authorization=(
            None
            if authorization_payload is None
            else ArmAuthorization(**dict(_mapping(authorization_payload, "authorization")))
        ),
        result=(
            None
            if result_payload is None
            else _result_from_payload(_mapping(result_payload, "simulation result"))
        ),
        disarm_reason=payload.get("disarm_reason"),
        journal_references=tuple(payload.get("journal_references", ())),
    )


def _result_from_payload(payload: Mapping[str, Any]) -> BreakoutSimulationResult:
    return BreakoutSimulationResult(
        run_id=payload["run_id"],
        status=payload["status"],
        data_resolution=payload["data_resolution"],
        opening_range_high=payload.get("opening_range_high"),
        trigger_threshold=payload.get("trigger_threshold"),
        trigger_price=payload.get("trigger_price"),
        frozen_day_low=payload.get("frozen_day_low"),
        conservative_entry=payload.get("conservative_entry"),
        per_share_risk=payload.get("per_share_risk"),
        shares=payload.get("shares"),
        entry_fill_price=payload.get("entry_fill_price"),
        protective_stop_price=payload.get("protective_stop_price"),
        exit_fill_price=payload.get("exit_fill_price"),
        realized_pnl=payload.get("realized_pnl"),
        protection_state=payload["protection_state"],
        idempotency_key=payload.get("idempotency_key"),
        critical_alert=payload.get("critical_alert"),
        audit_events=tuple(dict(item) for item in payload.get("audit_events", ())),
    )


def _authorization_payload(authorization: ArmAuthorization) -> dict[str, str]:
    return {
        "run_id": authorization.run_id,
        "fingerprint": authorization.fingerprint,
        "authorized_at": authorization.authorized_at,
        "expires_at": authorization.expires_at,
        "authorized_by": authorization.authorized_by,
    }


def _risk_policy_payload(policy: RiskPolicy) -> dict[str, Any]:
    return {
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
    }


def _risk_policy_from_payload(payload: Mapping[str, Any]) -> RiskPolicy:
    return RiskPolicy(**dict(payload))


def _journal_reference(record: JournalRecord) -> str:
    return f"journal_sequence:{record.sequence}"


def _stable_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise StrategyRunError("payload must be JSON-serializable") from exc


def _json_object(raw_json: str, field_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise StrategyRunError(f"{field_name} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise StrategyRunError(f"{field_name} must be a JSON object")
    return payload


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StrategyRunError(f"{field_name} must be an object")
    return value


def _is_risk_failure(reason: str) -> bool:
    return any(
        marker in reason
        for marker in (
            "risk distance",
            "calculated shares",
            "dollar risk",
            "share cap",
            "notional cap",
            "buying power",
            "concurrent position cap",
            "symbol exposure cap",
            "daily loss cap",
        )
    )


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StrategyRunError(f"{field_name} must be a non-empty identifier")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(character not in allowed for character in value):
        raise StrategyRunError(f"{field_name} contains unsupported characters")
    return value


def _positive_decimal_string(value: Any, field_name: str) -> str:
    try:
        from decimal import Decimal, InvalidOperation

        parsed = Decimal(value) if isinstance(value, str) else None
    except InvalidOperation as exc:
        raise StrategyRunError(f"{field_name} must be a decimal string") from exc
    if parsed is None or not parsed.is_finite() or parsed <= 0:
        raise StrategyRunError(f"{field_name} must be a positive decimal string")
    return value


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StrategyRunError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StrategyRunError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StrategyRunError(f"{field_name} must include a timezone")
    return parsed


def _parse_date(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise StrategyRunError(f"{field_name} must be YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise StrategyRunError(f"{field_name} must be YYYY-MM-DD") from exc


def _parse_time(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise StrategyRunError(f"{field_name} must be HH:MM:SS")
    try:
        datetime.strptime(value, "%H:%M:%S")
    except ValueError as exc:
        raise StrategyRunError(f"{field_name} must be HH:MM:SS") from exc
