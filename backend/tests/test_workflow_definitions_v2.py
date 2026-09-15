from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from test_workflow_dsl_v2 import valid_v2_workflow

from trading_oms_backend.typed_workflow_definitions import (
    SqliteWorkflowDefinitionStore,
    WorkflowDefinitionError,
    WorkflowDefinitionSaveRequest,
)


def test_sqlite_workflow_store_retains_immutable_v2_versions() -> None:
    with _store() as store:
        created = store.create_workflow(_request())
        updated_document = valid_v2_workflow()
        updated_document["workflow_id"] = "strategy-workflow-001"
        updated_document["nodes"][4]["config"] = {"minutes": 1}
        updated = store.update_workflow(
            "strategy-workflow-001",
            _request(
                document=updated_document,
                requested_at="2026-07-08T00:05:00Z",
                expected_version=1,
            ),
        )

        assert created.schema_version == 2
        assert created.version == 1
        assert created.checksum is not None
        assert updated.version == 2
        assert updated.checksum != created.checksum
        assert store.get_workflow("strategy-workflow-001") == updated
        assert store.get_workflow_version("strategy-workflow-001", 1) == created
        assert store.list_workflow_versions("strategy-workflow-001") == (created, updated)


def test_sqlite_v2_workflow_save_is_idempotent_for_same_timestamp_and_document() -> None:
    with _store() as store:
        first = store.create_workflow(_request())
        repeated = store.create_workflow(_request())

        assert repeated == first
        assert store.list_workflow_versions("strategy-workflow-001") == (first,)


def test_v2_outer_and_document_workflow_identifiers_must_match() -> None:
    document = valid_v2_workflow()

    with pytest.raises(WorkflowDefinitionError, match="workflow_id must match"):
        _request(document=document)


def _request(**overrides: object) -> WorkflowDefinitionSaveRequest:
    document = valid_v2_workflow()
    document["workflow_id"] = "strategy-workflow-001"
    values: dict[str, object] = {
        "schema_version": 2,
        "workflow_id": "strategy-workflow-001",
        "display_name": "First five minute breakout",
        "description": "Typed deterministic simulation workflow",
        "document": document,
        "requested_at": "2026-07-08T00:00:00Z",
    }
    values.update(overrides)
    return WorkflowDefinitionSaveRequest(**values)


class _StoreContext:
    def __init__(self) -> None:
        self._temporary = TemporaryDirectory()
        self.store = SqliteWorkflowDefinitionStore(
            Path(self._temporary.name) / "workflow-definitions.sqlite3"
        )

    def __enter__(self) -> SqliteWorkflowDefinitionStore:
        return self.store

    def __exit__(self, *_args: object) -> None:
        self._temporary.cleanup()


def _store() -> Iterator[SqliteWorkflowDefinitionStore]:
    return _StoreContext()
