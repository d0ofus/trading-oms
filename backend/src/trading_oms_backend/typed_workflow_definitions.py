from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from trading_oms_backend.typed_workflow_dsl import (
    FORBIDDEN_WORKFLOW_TOKENS,
    WorkflowDslError,
    canonical_workflow_json,
    parse_workflow_dsl_document,
)


class WorkflowDefinitionError(ValueError):
    """Raised when a saved visual workflow definition is invalid or unsafe."""


FORBIDDEN_METADATA_TOKENS = (*FORBIDDEN_WORKFLOW_TOKENS, "live trading")


@dataclass(frozen=True)
class WorkflowDefinitionSaveRequest:
    workflow_id: str
    display_name: str
    description: str
    document: Mapping[str, Any]
    requested_at: str
    schema_version: int = 1
    expected_version: int | None = None

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.workflow_id, "workflow_id")
        _validated_metadata_text(self.display_name, "display_name")
        _validated_metadata_text(self.description, "description")
        _parse_timestamp(self.requested_at, "requested_at")
        if self.expected_version is not None:
            _positive_integer(self.expected_version, "expected_version")
        document = _normalize_document(self.document)
        if document.get("schema_version") != self.schema_version:
            raise WorkflowDefinitionError(
                "workflow definition schema_version must match document schema_version"
            )
        if self.schema_version == 2 and document.get("workflow_id") != self.workflow_id:
            raise WorkflowDefinitionError(
                "workflow definition workflow_id must match document workflow_id"
            )
        _assert_json_serializable(self.to_payload(), "workflow definition save request")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "display_name": self.display_name,
            "description": self.description,
            "document": _normalize_document(self.document),
            "requested_at": self.requested_at,
            "expected_version": self.expected_version,
        }


@dataclass(frozen=True)
class WorkflowDefinitionRecord:
    workflow_id: str
    display_name: str
    description: str
    version: int
    created_at: str
    updated_at: str
    document: Mapping[str, Any]
    schema_version: int = 1
    checksum: str | None = None

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        _validated_identifier(self.workflow_id, "workflow_id")
        _validated_metadata_text(self.display_name, "display_name")
        _validated_metadata_text(self.description, "description")
        _positive_integer(self.version, "version")
        created_at = _parse_timestamp(self.created_at, "created_at")
        updated_at = _parse_timestamp(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise WorkflowDefinitionError("updated_at must not be before created_at")
        document = _normalize_document(self.document)
        if document.get("schema_version") != self.schema_version:
            raise WorkflowDefinitionError(
                "workflow definition schema_version must match document schema_version"
            )
        expected_checksum = _document_checksum(document)
        if self.schema_version == 2 and self.checksum != expected_checksum:
            raise WorkflowDefinitionError("schema-v2 workflow checksum must match the document")
        if self.schema_version == 1 and self.checksum is not None:
            raise WorkflowDefinitionError("schema-v1 workflow records do not include a checksum")
        _assert_json_serializable(self.to_json_dict(), "workflow definition record")

    @classmethod
    def from_json_dict(cls, payload: Mapping[str, Any]) -> WorkflowDefinitionRecord:
        return cls(
            schema_version=payload.get("schema_version", 1),
            workflow_id=_required_value(payload, "workflow_id"),
            display_name=_required_value(payload, "display_name"),
            description=_required_value(payload, "description"),
            version=_required_value(payload, "version"),
            created_at=_required_value(payload, "created_at"),
            updated_at=_required_value(payload, "updated_at"),
            document=_required_value(payload, "document"),
            checksum=payload.get("checksum"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "document": _normalize_document(self.document),
        }
        if self.schema_version == 2:
            payload["checksum"] = self.checksum
        return payload

    def matches_request(self, request: WorkflowDefinitionSaveRequest) -> bool:
        return (
            self.workflow_id == request.workflow_id
            and self.schema_version == request.schema_version
            and self.display_name == request.display_name
            and self.description == request.description
            and self.updated_at == request.requested_at
            and _normalize_document(self.document) == _normalize_document(request.document)
        )


class WorkflowDefinitionStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def create_workflow(
        self,
        request: WorkflowDefinitionSaveRequest,
    ) -> WorkflowDefinitionRecord:
        if not isinstance(request, WorkflowDefinitionSaveRequest):
            raise WorkflowDefinitionError("request must be WorkflowDefinitionSaveRequest")

        records = self._load_records()
        existing = records.get(request.workflow_id)
        if existing is not None:
            if existing.version == 1 and existing.matches_request(request):
                return existing
            raise WorkflowDefinitionError("conflicting duplicate workflow_id")

        record = WorkflowDefinitionRecord(
            workflow_id=request.workflow_id,
            display_name=request.display_name,
            description=request.description,
            version=1,
            created_at=request.requested_at,
            updated_at=request.requested_at,
            document=_normalize_document(request.document),
            schema_version=request.schema_version,
            checksum=(
                _document_checksum(request.document) if request.schema_version == 2 else None
            ),
        )
        records[record.workflow_id] = record
        self._write_records(records)
        return record

    def update_workflow(
        self,
        workflow_id: str,
        request: WorkflowDefinitionSaveRequest,
    ) -> WorkflowDefinitionRecord:
        _validated_identifier(workflow_id, "workflow_id")
        if not isinstance(request, WorkflowDefinitionSaveRequest):
            raise WorkflowDefinitionError("request must be WorkflowDefinitionSaveRequest")
        if workflow_id != request.workflow_id:
            raise WorkflowDefinitionError("path workflow_id must match body workflow_id")

        records = self._load_records()
        existing = records.get(workflow_id)
        if existing is None:
            raise WorkflowDefinitionError("unknown workflow_id")
        if existing.matches_request(request):
            return existing
        if _parse_timestamp(request.requested_at, "requested_at") < _parse_timestamp(
            existing.updated_at,
            "updated_at",
        ):
            raise WorkflowDefinitionError("requested_at must not be before current updated_at")

        record = WorkflowDefinitionRecord(
            workflow_id=request.workflow_id,
            display_name=request.display_name,
            description=request.description,
            version=existing.version + 1,
            created_at=existing.created_at,
            updated_at=request.requested_at,
            document=_normalize_document(request.document),
            schema_version=request.schema_version,
            checksum=(
                _document_checksum(request.document) if request.schema_version == 2 else None
            ),
        )
        records[record.workflow_id] = record
        self._write_records(records)
        return record

    def get_workflow(self, workflow_id: str) -> WorkflowDefinitionRecord:
        _validated_identifier(workflow_id, "workflow_id")
        record = self._load_records().get(workflow_id)
        if record is None:
            raise WorkflowDefinitionError("unknown workflow_id")
        return record

    def list_workflows(self) -> tuple[WorkflowDefinitionRecord, ...]:
        records = self._load_records()
        return tuple(records[workflow_id] for workflow_id in sorted(records))

    def _load_records(self) -> dict[str, WorkflowDefinitionRecord]:
        if not self._path.exists():
            return {}

        with self._path.open("r", encoding="utf-8") as workflow_file:
            try:
                payload = json.load(workflow_file)
            except json.JSONDecodeError as exc:
                raise WorkflowDefinitionError("workflow store must contain valid JSON") from exc

        if not isinstance(payload, Mapping):
            raise WorkflowDefinitionError("workflow store must be a JSON object")
        _validate_schema_version(payload.get("schema_version"))
        workflows = payload.get("workflows")
        if not isinstance(workflows, list):
            raise WorkflowDefinitionError("workflow store workflows must be a list")

        records: dict[str, WorkflowDefinitionRecord] = {}
        for item in workflows:
            if not isinstance(item, Mapping):
                raise WorkflowDefinitionError("workflow record must be a JSON object")
            record = WorkflowDefinitionRecord.from_json_dict(item)
            if record.workflow_id in records:
                raise WorkflowDefinitionError("duplicate workflow_id in workflow store")
            records[record.workflow_id] = record
        return records

    def _write_records(self, records: Mapping[str, WorkflowDefinitionRecord]) -> None:
        payload = {
            "schema_version": 1,
            "workflows": [record.to_json_dict() for record in records.values()],
        }
        _assert_json_serializable(payload, "workflow store")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_name(f"{self._path.name}.tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as workflow_file:
            json.dump(payload, workflow_file, allow_nan=False, indent=2, sort_keys=True)
            workflow_file.write("\n")
        temp_path.replace(self._path)


class SqliteWorkflowDefinitionStore:
    """Immutable, versioned workflow definitions backed by a local SQLite file."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS workflow_versions (
      workflow_id TEXT NOT NULL,
      version INTEGER NOT NULL,
      schema_version INTEGER NOT NULL,
      checksum TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      PRIMARY KEY (workflow_id, version)
    );

    CREATE TABLE IF NOT EXISTS workflow_heads (
      workflow_id TEXT PRIMARY KEY,
      version INTEGER NOT NULL,
      FOREIGN KEY (workflow_id, version)
        REFERENCES workflow_versions (workflow_id, version)
    );
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._initialize()

    def create_workflow(
        self,
        request: WorkflowDefinitionSaveRequest,
    ) -> WorkflowDefinitionRecord:
        if not isinstance(request, WorkflowDefinitionSaveRequest):
            raise WorkflowDefinitionError("request must be WorkflowDefinitionSaveRequest")
        if request.expected_version is not None:
            raise WorkflowDefinitionError("expected_version is only valid for updates")
        existing = self._optional_head(request.workflow_id)
        if existing is not None:
            if existing.version == 1 and existing.matches_request(request):
                return existing
            raise WorkflowDefinitionError("conflicting duplicate workflow_id")
        record = _record_from_request(request, version=1, created_at=request.requested_at)
        self._insert_version(record)
        return record

    def update_workflow(
        self,
        workflow_id: str,
        request: WorkflowDefinitionSaveRequest,
    ) -> WorkflowDefinitionRecord:
        _validated_identifier(workflow_id, "workflow_id")
        if not isinstance(request, WorkflowDefinitionSaveRequest):
            raise WorkflowDefinitionError("request must be WorkflowDefinitionSaveRequest")
        if workflow_id != request.workflow_id:
            raise WorkflowDefinitionError("path workflow_id must match body workflow_id")
        existing = self._optional_head(workflow_id)
        if existing is None:
            raise WorkflowDefinitionError("unknown workflow_id")
        if request.expected_version is None:
            raise WorkflowDefinitionError("expected_version is required for updates")
        if existing.matches_request(request) and request.expected_version in {
            existing.version,
            existing.version - 1,
        }:
            return existing
        if request.expected_version != existing.version:
            raise WorkflowDefinitionError(
                "expected_version does not match current workflow version"
            )
        if _parse_timestamp(request.requested_at, "requested_at") < _parse_timestamp(
            existing.updated_at,
            "updated_at",
        ):
            raise WorkflowDefinitionError("requested_at must not be before current updated_at")
        record = _record_from_request(
            request,
            version=existing.version + 1,
            created_at=existing.created_at,
        )
        self._insert_version(record)
        return record

    def get_workflow(self, workflow_id: str) -> WorkflowDefinitionRecord:
        _validated_identifier(workflow_id, "workflow_id")
        record = self._optional_head(workflow_id)
        if record is None:
            raise WorkflowDefinitionError("unknown workflow_id")
        return record

    def get_workflow_version(self, workflow_id: str, version: int) -> WorkflowDefinitionRecord:
        _validated_identifier(workflow_id, "workflow_id")
        _positive_integer(version, "version")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM workflow_versions
                WHERE workflow_id = ? AND version = ?
                """,
                (workflow_id, version),
            ).fetchone()
        if row is None:
            raise WorkflowDefinitionError("unknown workflow version")
        return _record_from_payload_json(str(row["payload_json"]))

    def list_workflows(self) -> tuple[WorkflowDefinitionRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT versions.payload_json
                FROM workflow_heads AS heads
                JOIN workflow_versions AS versions
                  ON versions.workflow_id = heads.workflow_id
                 AND versions.version = heads.version
                ORDER BY heads.workflow_id
                """
            ).fetchall()
        return tuple(_record_from_payload_json(str(row["payload_json"])) for row in rows)

    def list_workflow_versions(self, workflow_id: str) -> tuple[WorkflowDefinitionRecord, ...]:
        _validated_identifier(workflow_id, "workflow_id")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM workflow_versions
                WHERE workflow_id = ?
                ORDER BY version
                """,
                (workflow_id,),
            ).fetchall()
        return tuple(_record_from_payload_json(str(row["payload_json"])) for row in rows)

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(self._SCHEMA)

    def _optional_head(self, workflow_id: str) -> WorkflowDefinitionRecord | None:
        _validated_identifier(workflow_id, "workflow_id")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT versions.payload_json
                FROM workflow_heads AS heads
                JOIN workflow_versions AS versions
                  ON versions.workflow_id = heads.workflow_id
                 AND versions.version = heads.version
                WHERE heads.workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return None if row is None else _record_from_payload_json(str(row["payload_json"]))

    def _insert_version(self, record: WorkflowDefinitionRecord) -> None:
        payload_json = json.dumps(
            record.to_json_dict(),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                head = connection.execute(
                    "SELECT version FROM workflow_heads WHERE workflow_id = ?",
                    (record.workflow_id,),
                ).fetchone()
                observed = 0 if head is None else int(head["version"])
                if observed != record.version - 1:
                    raise WorkflowDefinitionError(
                        "expected_version does not match current workflow version"
                    )
                connection.execute(
                    """
                    INSERT INTO workflow_versions (
                      workflow_id, version, schema_version, checksum,
                      created_at, updated_at, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.workflow_id,
                        record.version,
                        record.schema_version,
                        record.checksum,
                        record.created_at,
                        record.updated_at,
                        payload_json,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO workflow_heads (workflow_id, version)
                    VALUES (?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET version = excluded.version
                    """,
                    (record.workflow_id, record.version),
                )
        except sqlite3.IntegrityError as exc:
            raise WorkflowDefinitionError("workflow version already exists") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _record_from_request(
    request: WorkflowDefinitionSaveRequest,
    *,
    version: int,
    created_at: str,
) -> WorkflowDefinitionRecord:
    return WorkflowDefinitionRecord(
        workflow_id=request.workflow_id,
        display_name=request.display_name,
        description=request.description,
        version=version,
        created_at=created_at,
        updated_at=request.requested_at,
        document=_normalize_document(request.document),
        schema_version=request.schema_version,
        checksum=_document_checksum(request.document) if request.schema_version == 2 else None,
    )


def _record_from_payload_json(payload_json: str) -> WorkflowDefinitionRecord:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise WorkflowDefinitionError("stored workflow version must contain valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise WorkflowDefinitionError("stored workflow version must be a JSON object")
    return WorkflowDefinitionRecord.from_json_dict(payload)


def _normalize_document(document: Mapping[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(document, allow_nan=False)
        normalized = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise WorkflowDefinitionError("workflow document must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise WorkflowDefinitionError("workflow document must be a JSON object")
    try:
        parse_workflow_dsl_document(normalized)
    except WorkflowDslError as exc:
        raise WorkflowDefinitionError(str(exc)) from exc
    return normalized


def _validate_schema_version(schema_version: Any) -> None:
    if isinstance(schema_version, bool) or schema_version not in {1, 2}:
        raise WorkflowDefinitionError("schema_version must be 1 or 2")


def _document_checksum(document: Mapping[str, Any]) -> str:
    try:
        canonical = canonical_workflow_json(document)
    except WorkflowDslError as exc:
        raise WorkflowDefinitionError(str(exc)) from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _required_value(payload: Mapping[str, Any], key: str) -> Any:
    try:
        return payload[key]
    except KeyError as exc:
        raise WorkflowDefinitionError(f"workflow record is missing {key}") from exc


def _validated_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowDefinitionError(f"{field_name} must be a non-empty string")
    if value.strip() != value:
        raise WorkflowDefinitionError(
            f"{field_name} must not contain leading or trailing whitespace"
        )
    _reject_forbidden_metadata(value, field_name)
    return value


def _validated_metadata_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowDefinitionError(f"{field_name} must be a non-empty string")
    _reject_forbidden_metadata(value, field_name)
    return value


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkflowDefinitionError(f"{field_name} must be a positive integer")
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowDefinitionError(f"{field_name} must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkflowDefinitionError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WorkflowDefinitionError(f"{field_name} must include a timezone")
    return parsed


def _reject_forbidden_metadata(value: str, field_name: str) -> None:
    normalized = value.lower().replace("-", "_")
    for token in FORBIDDEN_METADATA_TOKENS:
        if token in normalized:
            raise WorkflowDefinitionError(f"{field_name} contains forbidden workflow token {token}")


def _assert_json_serializable(payload: Mapping[str, Any], payload_name: str) -> None:
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowDefinitionError(f"{payload_name} must be JSON-serializable") from exc
