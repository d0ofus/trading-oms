from __future__ import annotations

import argparse
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

    def schema_version(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        version = None if row is None else row[0]
        if version != 1:
            raise LocalPersistenceError("local persistence schema_version must be 1")
        return 1

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
