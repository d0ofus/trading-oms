from __future__ import annotations

from typing import cast

import pytest

from trading_oms_backend.workflow_dsl import WorkflowDslError, parse_workflow_dsl_document


def test_workflow_dsl_accepts_safe_simulation_document() -> None:
    document = parse_workflow_dsl_document(_valid_workflow_dsl())

    assert document.workflow_id == "visual-simulation-workflow"
    assert [node.type for node in document.nodes] == [
        "replay_source",
        "bar_builder",
        "strategy_trigger",
        "risk_check",
        "approval_ticket",
        "fake_broker",
        "position_update",
        "alert",
        "audit_sink",
    ]


@pytest.mark.parametrize(
    ("field_path", "value", "message"),
    [
        (("mode",), "live", "mode"),
        (("broker",), "ibkr", "forbidden workflow token ibkr"),
        (("safety_gates", "live_trading_enabled"), True, "live_trading_enabled"),
        (("safety_gates", "broker_transport_allowed"), True, "broker_transport_allowed"),
        (("safety_gates", "arbitrary_code_allowed"), True, "arbitrary_code_allowed"),
    ],
)
def test_workflow_dsl_rejects_unsafe_top_level_values(
    field_path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    payload = _valid_workflow_dsl()
    _set_nested(payload, field_path, value)

    with pytest.raises(WorkflowDslError, match=message):
        parse_workflow_dsl_document(payload)


def test_workflow_dsl_rejects_missing_required_nodes() -> None:
    payload = _valid_workflow_dsl()
    payload["nodes"] = [node for node in payload["nodes"] if node["type"] != "risk_check"]

    with pytest.raises(WorkflowDslError, match="missing required node types: risk_check"):
        parse_workflow_dsl_document(payload)


def test_workflow_dsl_rejects_unsupported_nodes_and_forbidden_shapes() -> None:
    payload = _valid_workflow_dsl()
    payload["nodes"].append(
        {
            "id": "custom-node",
            "type": "spreadsheet_macro",
            "required_for_risk_increasing_path": True,
        }
    )

    with pytest.raises(WorkflowDslError, match="unsupported node types: spreadsheet_macro"):
        parse_workflow_dsl_document(payload)

    payload = _valid_workflow_dsl()
    payload["nodes"].append(
        {
            "id": "unsafe-node",
            "type": "submit_order",
            "required_for_risk_increasing_path": True,
        }
    )

    with pytest.raises(WorkflowDslError, match="forbidden workflow token submit"):
        parse_workflow_dsl_document(payload)


def test_workflow_dsl_rejects_unknown_edge_endpoint_and_cycles() -> None:
    payload = _valid_workflow_dsl()
    payload["edges"].append({"source": "risk-check", "target": "missing-node"})

    with pytest.raises(WorkflowDslError, match="unknown node"):
        parse_workflow_dsl_document(payload)

    payload = _valid_workflow_dsl()
    payload["edges"].append({"source": "audit-sink", "target": "risk-check"})

    with pytest.raises(WorkflowDslError, match="cycle"):
        parse_workflow_dsl_document(payload)


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


def _set_nested(payload: dict[str, object], field_path: tuple[str, ...], value: object) -> None:
    target = payload
    for key in field_path[:-1]:
        target = cast(dict[str, object], target[key])
    target[field_path[-1]] = value
