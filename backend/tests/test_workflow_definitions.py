from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import pytest

from trading_oms_backend.workflow_definitions import (
    WorkflowDefinitionError,
    WorkflowDefinitionSaveRequest,
    WorkflowDefinitionStore,
)

FORBIDDEN_PAYLOAD_KEYS = {
    "account",
    "account_id",
    "api_key",
    "authorization",
    "broker_host",
    "broker_port",
    "certificate",
    "connect_url",
    "credential",
    "host",
    "password",
    "place_order_url",
    "port",
    "private_key",
    "route",
    "secret",
    "socket",
    "submit_url",
    "token",
    "transmit",
    "transmit_url",
}


@pytest.fixture
def workflow_store_path() -> Iterator[Path]:
    root = Path(__file__).resolve().parents[1] / ".test-tmp"
    root.mkdir(exist_ok=True)
    try:
        with TemporaryDirectory(dir=root) as temp_dir:
            yield Path(temp_dir) / "workflows.json"
    finally:
        try:
            root.rmdir()
        except OSError:
            pass


def test_workflow_definition_store_creates_lists_loads_and_persists_records(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)

    record = store.create_workflow(_save_request())

    assert record.to_json_dict() == {
        "schema_version": 1,
        "workflow_id": "workflow-001",
        "display_name": "Opening breakout simulation",
        "description": "Validated visual simulation workflow",
        "version": 1,
        "created_at": "2026-07-08T00:00:00Z",
        "updated_at": "2026-07-08T00:00:00Z",
        "document": _valid_workflow_dsl(),
    }
    assert store.list_workflows() == (record,)
    assert store.get_workflow("workflow-001") == record

    restored = WorkflowDefinitionStore(workflow_store_path)
    assert restored.list_workflows() == (record,)
    assert restored.get_workflow("workflow-001") == record


def test_workflow_definition_create_is_idempotent_for_identical_payload(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)

    first = store.create_workflow(_save_request())
    second = store.create_workflow(_save_request())

    assert second == first
    assert store.list_workflows() == (first,)


def test_workflow_definition_create_rejects_conflicting_duplicate_id(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)
    store.create_workflow(_save_request())

    with pytest.raises(WorkflowDefinitionError, match="conflicting duplicate workflow_id"):
        store.create_workflow(_save_request(display_name="Alternate simulation"))


def test_workflow_definition_update_versions_records_and_is_idempotent(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)
    created = store.create_workflow(_save_request())

    updated = store.update_workflow(
        "workflow-001",
        _save_request(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
        ),
    )
    repeated = store.update_workflow(
        "workflow-001",
        _save_request(
            description="Updated local visual workflow definition",
            requested_at="2026-07-08T00:05:00Z",
        ),
    )

    assert created.version == 1
    assert updated.version == 2
    assert updated.created_at == "2026-07-08T00:00:00Z"
    assert updated.updated_at == "2026-07-08T00:05:00Z"
    assert updated.description == "Updated local visual workflow definition"
    assert repeated == updated
    assert store.get_workflow("workflow-001") == updated


def test_workflow_definition_update_rejects_unknown_or_mismatched_workflows(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)

    with pytest.raises(WorkflowDefinitionError, match="unknown workflow_id"):
        store.update_workflow("workflow-001", _save_request())

    store.create_workflow(_save_request())
    with pytest.raises(WorkflowDefinitionError, match="path workflow_id must match body"):
        store.update_workflow("workflow-001", _save_request(workflow_id="workflow-002"))


def test_workflow_definition_store_rejects_invalid_or_unsafe_documents(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)

    unsafe = _valid_workflow_dsl()
    safety_gates = cast(dict[str, object], unsafe["safety_gates"])
    safety_gates["live_trading_enabled"] = True

    with pytest.raises(WorkflowDefinitionError, match="live_trading_enabled"):
        store.create_workflow(_save_request(document=unsafe))

    forbidden = _valid_workflow_dsl()
    nodes = cast(list[dict[str, object]], forbidden["nodes"])
    nodes.append(
        {
            "id": "unsafe-node",
            "type": "submit_order",
            "required_for_risk_increasing_path": True,
        }
    )

    with pytest.raises(WorkflowDefinitionError, match="forbidden workflow token submit"):
        store.create_workflow(_save_request(document=forbidden))

    assert store.list_workflows() == ()


def test_workflow_definition_store_rejects_secret_or_broker_shaped_metadata(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)

    unsafe_request_factories = [
        lambda: _save_request(workflow_id="ibkr-workflow"),
        lambda: _save_request(display_name="Credential workflow"),
        lambda: _save_request(description="Route order later"),
    ]

    for request_factory in unsafe_request_factories:
        with pytest.raises(WorkflowDefinitionError):
            store.create_workflow(request_factory())

    assert store.list_workflows() == ()


def test_workflow_definition_payloads_exclude_broker_network_and_secret_affordances(
    workflow_store_path: Path,
) -> None:
    store = WorkflowDefinitionStore(workflow_store_path)
    record = store.create_workflow(_save_request())

    assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(_all_payload_keys(record.to_json_dict()))


def test_workflow_definitions_module_does_not_define_transport_execution_or_http_behavior() -> None:
    import trading_oms_backend.workflow_definitions as workflow_definitions

    source = inspect.getsource(workflow_definitions).lower()
    forbidden_source_tokens = [
        "@app.post",
        "@app.put",
        "@app.patch",
        "@app.delete",
        "import socket",
        "from socket",
        "httpx",
        "requests",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "place_order",
        "submit_order",
        "transmit_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


def _save_request(**overrides: Any) -> WorkflowDefinitionSaveRequest:
    values = {
        "workflow_id": "workflow-001",
        "display_name": "Opening breakout simulation",
        "description": "Validated visual simulation workflow",
        "document": _valid_workflow_dsl(),
        "requested_at": "2026-07-08T00:00:00Z",
    }
    values.update(overrides)
    return WorkflowDefinitionSaveRequest(**values)


def _valid_workflow_dsl() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "visual-simulation-workflow",
        "mode": "simulation",
        "runtime": "preview_only",
        "broker": "fake_broker_only",
        "nodes": [
            {
                "id": "replay-source",
                "type": "replay_source",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "bar-builder",
                "type": "bar_builder",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "strategy-trigger",
                "type": "strategy_trigger",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "risk-check",
                "type": "risk_check",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "approval-ticket",
                "type": "approval_ticket",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "fake-broker",
                "type": "fake_broker",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "position-update",
                "type": "position_update",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "alert",
                "type": "alert",
                "required_for_risk_increasing_path": True,
            },
            {
                "id": "audit-sink",
                "type": "audit_sink",
                "required_for_risk_increasing_path": True,
            },
        ],
        "edges": [
            {"source": "replay-source", "target": "bar-builder"},
            {"source": "bar-builder", "target": "strategy-trigger"},
            {"source": "strategy-trigger", "target": "risk-check"},
            {"source": "risk-check", "target": "approval-ticket"},
            {"source": "approval-ticket", "target": "fake-broker"},
            {"source": "fake-broker", "target": "position-update"},
            {"source": "position-update", "target": "alert"},
            {"source": "alert", "target": "audit-sink"},
        ],
        "safety_gates": {
            "risk_check_required": True,
            "manual_approval_required": True,
            "audit_sink_required": True,
            "broker_transport_allowed": False,
            "live_trading_enabled": False,
            "arbitrary_code_allowed": False,
        },
    }


def _all_payload_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested_value in value.values():
            keys.update(_all_payload_keys(nested_value))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_all_payload_keys(item))
        return keys
    return set()
