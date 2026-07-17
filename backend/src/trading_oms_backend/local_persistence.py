from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_oms_backend.event_journal import JournalRecord
from trading_oms_backend.read_models import OperationsReadModel
from trading_oms_backend.workflow_definitions import WorkflowDefinitionRecord
from trading_oms_backend.workflow_simulation_runs import WorkflowSimulationRunRecord


class LocalPersistenceError(ValueError):
    """Raised when local persistence would violate schema or safety rules."""


MIGRATION_APPLIED_AT = "1970-01-01T00:00:00Z"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_definitions (
  workflow_id TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_simulation_runs (
  run_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approval_ticket_id TEXT,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_simulation_runs_workflow_id
  ON workflow_simulation_runs (workflow_id);

CREATE TABLE IF NOT EXISTS read_model_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  recorded_at TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_index (
  sequence INTEGER PRIMARY KEY,
  event_type TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  run_id TEXT,
  symbol TEXT,
  order_id TEXT,
  ticket_id TEXT,
  severity TEXT,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_journal_index_event_type
  ON journal_index (event_type);

CREATE INDEX IF NOT EXISTS idx_journal_index_run_id
  ON journal_index (run_id);

CREATE INDEX IF NOT EXISTS idx_journal_index_symbol
  ON journal_index (symbol);

CREATE INDEX IF NOT EXISTS idx_journal_index_order_id
  ON journal_index (order_id);

CREATE INDEX IF NOT EXISTS idx_journal_index_ticket_id
  ON journal_index (ticket_id);

CREATE INDEX IF NOT EXISTS idx_journal_index_severity
  ON journal_index (severity);
"""

MIGRATION_2_SQL = """
CREATE TABLE IF NOT EXISTS workflow_simulation_run_evidence (
  run_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  expected_workflow_version INTEGER NOT NULL,
  request_sha256 TEXT NOT NULL,
  request_json TEXT NOT NULL,
  evidence_state TEXT NOT NULL,
  record_json TEXT,
  journal_manifest_json TEXT,
  journal_manifest_sha256 TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_simulation_run_evidence_workflow
  ON workflow_simulation_run_evidence (workflow_id, updated_at, run_id);
"""

WORKFLOW_SIMULATION_REQUEST_KEYS = {
    "schema_version",
    "workflow_id",
    "expected_workflow_version",
    "run_id",
    "requested_at",
    "evaluated_at",
    "approval_expires_at",
    "replay_input_reference",
}

SECRET_KEY_TOKENS = {
    "api_key",
    "apikey",
    "authorization",
    "certificate",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
}

FORBIDDEN_KEY_TOKENS = {
    "account_id",
    "broker_host",
    "connect_url",
    "place_order_url",
    "route_url",
    "submit_url",
    "transmit_url",
}

FALSE_ONLY_BOOLEAN_KEYS = {
    "arbitrary_code_allowed",
    "broker_transport_allowed",
    "live_trading_authorized",
    "live_trading_enabled",
}

FORBIDDEN_TEXT_TOKENS = {
    "account_id",
    "api_key",
    "authorization:",
    "bearer ",
    "broker_host",
    "eval(",
    "eval:",
    "ibkr connect",
    "javascript:",
    "password:",
    "password=",
    "place_order",
    "private_key",
    "route_order",
    "secret:",
    "secret=",
    "submit_order",
    "token:",
    "token=",
    "transmit_order",
}


@dataclass(frozen=True)
class JournalIndexEntry:
    sequence: int
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    run_id: str | None = None
    symbol: str | None = None
    order_id: str | None = None
    ticket_id: str | None = None
    severity: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _positive_integer(self.sequence, "sequence")
        _validated_identifier(self.event_type, "event_type")
        _parse_timestamp(self.timestamp, "timestamp")
        for field_name in ("run_id", "symbol", "order_id", "ticket_id", "severity"):
            value = getattr(self, field_name)
            if value is not None:
                _validated_identifier(value, field_name)
        _stable_payload_json(self.payload, "journal index payload")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "ticket_id": self.ticket_id,
            "severity": self.severity,
            "payload": _normalized_payload(self.payload, "journal index payload"),
        }


class LocalSqlitePersistenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (1, MIGRATION_APPLIED_AT),
            )
            connection.executescript(MIGRATION_2_SQL)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (2, MIGRATION_APPLIED_AT),
            )

    def schema_version(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        version = None if row is None else row[0]
        if version != 2:
            raise LocalPersistenceError("local persistence schema_version must be 2")
        return 2

    def put_workflow_definition(self, record: WorkflowDefinitionRecord) -> None:
        if not isinstance(record, WorkflowDefinitionRecord):
            raise LocalPersistenceError("record must be WorkflowDefinitionRecord")
        payload_json = _stable_payload_json(
            record.to_json_dict(),
            "workflow definition payload",
        )
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO workflow_definitions (
                  workflow_id, version, updated_at, payload_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (record.workflow_id, record.version, record.updated_at, payload_json),
            )

    def list_workflow_definitions(self) -> tuple[dict[str, Any], ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM workflow_definitions
                ORDER BY workflow_id
                """,
            ).fetchall()
        return tuple(_json_dict(row["payload_json"], "workflow definition payload") for row in rows)

    def put_workflow_simulation_run(self, record: WorkflowSimulationRunRecord) -> None:
        if not isinstance(record, WorkflowSimulationRunRecord):
            raise LocalPersistenceError("record must be WorkflowSimulationRunRecord")
        payload_json = _stable_payload_json(
            record.to_json_dict(),
            "workflow simulation run payload",
        )
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO workflow_simulation_runs (
                  run_id, workflow_id, status, updated_at, approval_ticket_id, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.workflow_id,
                    record.status,
                    record.updated_at,
                    record.approval_ticket_id,
                    payload_json,
                ),
            )

    def list_workflow_simulation_runs(self, workflow_id: str) -> tuple[dict[str, Any], ...]:
        _validated_identifier(workflow_id, "workflow_id")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM workflow_simulation_runs
                WHERE workflow_id = ?
                ORDER BY updated_at, run_id
                """,
                (workflow_id,),
            ).fetchall()
        return tuple(
            _json_dict(row["payload_json"], "workflow simulation run payload") for row in rows
        )

    def reserve_workflow_simulation_run(
        self,
        request_payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        request = _normalized_payload(
            request_payload,
            "workflow simulation run request",
        )
        _validate_workflow_simulation_request(request)
        request_json = _stable_payload_json(request, "workflow simulation run request")
        request_sha256 = _sha256(request_json)
        run_id = request["run_id"]
        workflow_id = request["workflow_id"]
        expected_workflow_version = request["expected_workflow_version"]
        created_at = request["requested_at"]
        updated_at = request["evaluated_at"]

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM workflow_simulation_run_evidence
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            reservation_created = row is None
            if reservation_created:
                connection.execute(
                    """
                    INSERT INTO workflow_simulation_run_evidence (
                      run_id, workflow_id, expected_workflow_version,
                      request_sha256, request_json, evidence_state,
                      record_json, journal_manifest_json, journal_manifest_sha256,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        run_id,
                        workflow_id,
                        expected_workflow_version,
                        request_sha256,
                        request_json,
                        created_at,
                        updated_at,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT *
                    FROM workflow_simulation_run_evidence
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
            evidence = _workflow_simulation_evidence_from_row(row)
            if evidence["request_sha256"] != request_sha256 or evidence["request"] != request:
                raise LocalPersistenceError("conflicting workflow simulation run_id")
            return evidence, reservation_created

    def finalize_workflow_simulation_run(
        self,
        run_id: str,
        record: WorkflowSimulationRunRecord,
        journal_records: tuple[JournalRecord, ...],
    ) -> dict[str, Any]:
        _validated_identifier(run_id, "run_id")
        if not isinstance(record, WorkflowSimulationRunRecord):
            raise LocalPersistenceError("record must be WorkflowSimulationRunRecord")
        if record.run_id != run_id:
            raise LocalPersistenceError("record run_id must match reserved run_id")
        if not isinstance(journal_records, tuple) or not journal_records:
            raise LocalPersistenceError("journal_records must be a non-empty tuple")
        for journal_record in journal_records:
            if not isinstance(journal_record, JournalRecord):
                raise LocalPersistenceError("journal_records must contain JournalRecord values")

        record_json = _stable_payload_json(
            record.to_json_dict(),
            "workflow simulation run record",
        )
        manifest = [journal_record.to_json_dict() for journal_record in journal_records]
        manifest_json = _stable_json_value(manifest, "workflow simulation journal manifest")
        manifest_sha256 = _sha256(manifest_json)

        self.initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM workflow_simulation_run_evidence
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise LocalPersistenceError("unknown workflow simulation run reservation")
            evidence = _workflow_simulation_evidence_from_row(row)
            if evidence["evidence_state"] != "pending":
                raise LocalPersistenceError("workflow simulation run evidence is already finalized")
            request = evidence["request"]
            if record.workflow_id != request["workflow_id"]:
                raise LocalPersistenceError("record workflow_id must match reserved workflow_id")
            connection.execute(
                """
                UPDATE workflow_simulation_run_evidence
                SET evidence_state = 'committed',
                    record_json = ?,
                    journal_manifest_json = ?,
                    journal_manifest_sha256 = ?,
                    updated_at = ?
                WHERE run_id = ? AND evidence_state = 'pending'
                """,
                (
                    record_json,
                    manifest_json,
                    manifest_sha256,
                    record.updated_at,
                    run_id,
                ),
            )
            finalized = connection.execute(
                """
                SELECT *
                FROM workflow_simulation_run_evidence
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            return _workflow_simulation_evidence_from_row(finalized)

    def get_workflow_simulation_run_evidence(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:
        _validated_identifier(run_id, "run_id")
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM workflow_simulation_run_evidence
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _workflow_simulation_evidence_from_row(row)

    def list_workflow_simulation_run_evidence(
        self,
        workflow_id: str,
    ) -> tuple[dict[str, Any], ...]:
        _validated_identifier(workflow_id, "workflow_id")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM workflow_simulation_run_evidence
                WHERE workflow_id = ?
                ORDER BY updated_at, run_id
                """,
                (workflow_id,),
            ).fetchall()
        return tuple(_workflow_simulation_evidence_from_row(row) for row in rows)

    def put_operations_read_model(
        self,
        snapshot_id: str,
        model: OperationsReadModel,
        *,
        recorded_at: str,
    ) -> None:
        _validated_identifier(snapshot_id, "snapshot_id")
        _parse_timestamp(recorded_at, "recorded_at")
        if not isinstance(model, OperationsReadModel):
            raise LocalPersistenceError("model must be OperationsReadModel")
        payload_json = _stable_payload_json(model.to_json_dict(), "operations read model payload")
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO read_model_snapshots (
                  snapshot_id, recorded_at, payload_json
                )
                VALUES (?, ?, ?)
                """,
                (snapshot_id, recorded_at, payload_json),
            )

    def get_operations_read_model(self, snapshot_id: str) -> dict[str, Any]:
        _validated_identifier(snapshot_id, "snapshot_id")
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM read_model_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise LocalPersistenceError("unknown read model snapshot_id")
        return _json_dict(row["payload_json"], "operations read model payload")

    def index_journal_records(self, records: Iterable[JournalRecord]) -> None:
        entries = tuple(_journal_index_entry(record) for record in records)
        self.initialize()
        with self._connect() as connection:
            for entry in entries:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO journal_index (
                      sequence, event_type, timestamp, run_id, symbol, order_id, ticket_id,
                      severity, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.sequence,
                        entry.event_type,
                        entry.timestamp,
                        entry.run_id,
                        entry.symbol,
                        entry.order_id,
                        entry.ticket_id,
                        entry.severity,
                        _stable_payload_json(entry.payload, "journal index payload"),
                    ),
                )

    def query_journal_index(
        self,
        *,
        event_type: str | None = None,
        run_id: str | None = None,
        symbol: str | None = None,
        order_id: str | None = None,
        ticket_id: str | None = None,
        severity: str | None = None,
    ) -> tuple[JournalIndexEntry, ...]:
        filters = {
            "event_type": event_type,
            "run_id": run_id,
            "symbol": symbol,
            "order_id": order_id,
            "ticket_id": ticket_id,
            "severity": severity,
        }
        clauses: list[str] = []
        values: list[str] = []
        for field_name, value in filters.items():
            if value is None:
                continue
            _validated_identifier(value, field_name)
            clauses.append(f"{field_name} = ?")
            values.append(value)

        where_sql = "" if not clauses else f"WHERE {' AND '.join(clauses)}"
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT sequence, event_type, timestamp, run_id, symbol, order_id, ticket_id,
                       severity, payload_json
                FROM journal_index
                {where_sql}
                ORDER BY sequence
                """,
                values,
            ).fetchall()
        return tuple(_journal_index_entry_from_row(row) for row in rows)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading OMS local persistence setup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="initialize the local SQLite schema")
    init_parser.add_argument("--database", required=True, help="path to the local SQLite file")

    args = parser.parse_args(argv)
    if args.command == "init":
        LocalSqlitePersistenceStore(args.database).initialize()
        return 0

    raise LocalPersistenceError("unsupported local persistence command")


def _journal_index_entry(record: JournalRecord) -> JournalIndexEntry:
    if not isinstance(record, JournalRecord):
        raise LocalPersistenceError("record must be JournalRecord")
    payload = _normalized_payload(record.payload, "journal index payload")
    return JournalIndexEntry(
        sequence=record.sequence,
        event_type=record.event_type,
        timestamp=record.timestamp,
        payload=payload,
        run_id=_extract_index_value(payload, ("run_id",)),
        symbol=_extract_index_value(payload, ("symbol",)),
        order_id=_extract_index_value(payload, ("order_id",)),
        ticket_id=_extract_index_value(payload, ("ticket_id", "approval_ticket_id")),
        severity=_extract_index_value(payload, ("severity",)),
    )


def _journal_index_entry_from_row(row: sqlite3.Row) -> JournalIndexEntry:
    return JournalIndexEntry(
        sequence=row["sequence"],
        event_type=row["event_type"],
        timestamp=row["timestamp"],
        run_id=row["run_id"],
        symbol=row["symbol"],
        order_id=row["order_id"],
        ticket_id=row["ticket_id"],
        severity=row["severity"],
        payload=_json_dict(row["payload_json"], "journal index payload"),
    )


def _extract_index_value(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key, value in payload.items():
        normalized_key = _normalized_key(str(key))
        if normalized_key in keys and isinstance(value, str) and value.strip():
            return value
        if isinstance(value, Mapping):
            nested = _extract_index_value(value, keys)
            if nested is not None:
                return nested
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    nested = _extract_index_value(item, keys)
                    if nested is not None:
                        return nested
    return None


def _stable_payload_json(payload: Mapping[str, Any], payload_name: str) -> str:
    normalized = _normalized_payload(payload, payload_name)
    return json.dumps(
        normalized,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _stable_json_value(value: Any, value_name: str) -> str:
    try:
        normalized = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise LocalPersistenceError(f"{value_name} must be JSON-serializable") from exc
    _reject_unsafe_content(normalized, ())
    return json.dumps(
        normalized,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalized_payload(payload: Mapping[str, Any], payload_name: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(payload, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise LocalPersistenceError(f"{payload_name} must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise LocalPersistenceError(f"{payload_name} must be a JSON object")
    _reject_unsafe_content(normalized, ())
    return normalized


def _json_dict(raw_json: str, payload_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise LocalPersistenceError(f"{payload_name} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise LocalPersistenceError(f"{payload_name} must be a JSON object")
    _reject_unsafe_content(payload, ())
    return payload


def _json_value(raw_json: str, value_name: str) -> Any:
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise LocalPersistenceError(f"{value_name} must contain valid JSON") from exc
    _reject_unsafe_content(value, ())
    return value


def _workflow_simulation_evidence_from_row(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        raise LocalPersistenceError("workflow simulation evidence row is missing")
    request = _json_dict(row["request_json"], "workflow simulation run request")
    _validate_workflow_simulation_request(request)
    request_json = _stable_payload_json(request, "workflow simulation run request")
    if row["request_sha256"] != _sha256(request_json):
        raise LocalPersistenceError("workflow simulation request digest is invalid")
    if (
        row["run_id"] != request["run_id"]
        or row["workflow_id"] != request["workflow_id"]
        or row["expected_workflow_version"] != request["expected_workflow_version"]
    ):
        raise LocalPersistenceError("workflow simulation request attribution is inconsistent")
    created_at = _parse_timestamp(row["created_at"], "created_at")
    updated_at = _parse_timestamp(row["updated_at"], "updated_at")
    if updated_at < created_at:
        raise LocalPersistenceError("workflow simulation evidence timestamps are inconsistent")

    state = row["evidence_state"]
    if state not in {"pending", "committed"}:
        raise LocalPersistenceError("workflow simulation evidence_state is invalid")
    optional_values = (
        row["record_json"],
        row["journal_manifest_json"],
        row["journal_manifest_sha256"],
    )
    if state == "pending" and any(value is not None for value in optional_values):
        raise LocalPersistenceError("pending workflow simulation evidence is inconsistent")
    if state == "committed" and any(value is None for value in optional_values):
        raise LocalPersistenceError("committed workflow simulation evidence is incomplete")

    record = None
    manifest = None
    manifest_sha256 = row["journal_manifest_sha256"]
    if state == "committed":
        record = _json_dict(row["record_json"], "workflow simulation run record")
        manifest = _json_value(
            row["journal_manifest_json"],
            "workflow simulation journal manifest",
        )
        if not isinstance(manifest, list) or not manifest:
            raise LocalPersistenceError(
                "workflow simulation journal manifest must be a non-empty list"
            )
        if not all(isinstance(item, dict) for item in manifest):
            raise LocalPersistenceError(
                "workflow simulation journal manifest must contain JSON objects"
            )
        manifest_json = _stable_json_value(
            manifest,
            "workflow simulation journal manifest",
        )
        if manifest_sha256 != _sha256(manifest_json):
            raise LocalPersistenceError("workflow simulation journal manifest digest is invalid")

    return {
        "run_id": row["run_id"],
        "workflow_id": row["workflow_id"],
        "expected_workflow_version": row["expected_workflow_version"],
        "request_sha256": row["request_sha256"],
        "request": request,
        "evidence_state": state,
        "record": record,
        "journal_manifest": manifest,
        "journal_manifest_sha256": manifest_sha256,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _validate_workflow_simulation_request(request: Mapping[str, Any]) -> None:
    if set(request) != WORKFLOW_SIMULATION_REQUEST_KEYS:
        raise LocalPersistenceError("workflow simulation run request fields are invalid")
    if request["schema_version"] != 1 or isinstance(request["schema_version"], bool):
        raise LocalPersistenceError("workflow simulation run request schema_version must be 1")
    _validated_identifier(request["workflow_id"], "workflow_id")
    _positive_integer(request["expected_workflow_version"], "expected_workflow_version")
    _validated_identifier(request["run_id"], "run_id")
    requested_at = _parse_timestamp(request["requested_at"], "requested_at")
    evaluated_at = _parse_timestamp(request["evaluated_at"], "evaluated_at")
    approval_expires_at = _parse_timestamp(
        request["approval_expires_at"],
        "approval_expires_at",
    )
    if evaluated_at < requested_at or approval_expires_at <= evaluated_at:
        raise LocalPersistenceError("workflow simulation run request timestamps are invalid")
    _validated_identifier(request["replay_input_reference"], "replay_input_reference")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reject_unsafe_content(value: Any, path: tuple[str, ...]) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = _normalized_key(str(raw_key))
            _reject_unsafe_key(key, path)
            if key in FALSE_ONLY_BOOLEAN_KEYS and nested is not False:
                raise LocalPersistenceError(f"{'.'.join((*path, key))} must remain false")
            _reject_unsafe_content(nested, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_content(item, (*path, str(index)))
    elif isinstance(value, str):
        _reject_unsafe_text(value, path)


def _reject_unsafe_key(key: str, path: tuple[str, ...]) -> None:
    if key in SECRET_KEY_TOKENS or any(token in key for token in SECRET_KEY_TOKENS):
        raise LocalPersistenceError(f"{'.'.join((*path, key))} must not store secret fields")
    if key in FORBIDDEN_KEY_TOKENS:
        raise LocalPersistenceError(f"{'.'.join((*path, key))} must not store broker fields")
    if key in {"live_mode", "route_live", "submit_live", "transmit_live"}:
        raise LocalPersistenceError(f"{'.'.join((*path, key))} must not store live controls")


def _reject_unsafe_text(value: str, path: tuple[str, ...]) -> None:
    normalized = value.lower().replace("-", "_")
    if any(token in normalized for token in FORBIDDEN_TEXT_TOKENS):
        field_name = ".".join(path) if path else "payload"
        raise LocalPersistenceError(f"{field_name} contains forbidden persistence text")


def _normalized_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _validate_schema_version(schema_version: int) -> None:
    if isinstance(schema_version, bool) or schema_version != 1:
        raise LocalPersistenceError("schema_version must be 1")


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LocalPersistenceError(f"{field_name} must be a positive integer")
    return value


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalPersistenceError(f"{field_name} must be a non-empty string")
    if value.strip() != value:
        raise LocalPersistenceError(f"{field_name} must not contain leading or trailing whitespace")
    _reject_unsafe_text(value, (field_name,))
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _validated_identifier(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocalPersistenceError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LocalPersistenceError(f"{field_name} must include a timezone")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
