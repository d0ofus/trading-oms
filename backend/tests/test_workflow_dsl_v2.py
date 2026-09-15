from __future__ import annotations

from copy import deepcopy

import pytest

from trading_oms_backend.typed_workflow_dsl import (
    WorkflowDslError,
    WorkflowDslV2Document,
    canonical_workflow_json,
    parse_workflow_dsl_document,
    workflow_node_catalog_payload,
)


def test_v2_catalog_exposes_typed_ports_and_no_transport_capability() -> None:
    catalog = workflow_node_catalog_payload()

    assert catalog["schema_version"] == 2
    by_type = {item["type"]: item for item in catalog["nodes"]}
    assert by_type["opening_range_high"]["outputs"] == {"price": "Price"}
    assert by_type["long_risk_size"]["inputs"]["maximum_dollar_loss"] == "Money"
    assert by_type["fake_broker"]["inputs"]["plan"] == "ProtectedOrderPlan"
    assert by_type["fake_broker"]["execution_capability"] == "simulation_only"
    assert all(item["execution_capability"] != "external_transport" for item in catalog["nodes"])


def test_v2_document_parses_port_edges_and_is_canonical() -> None:
    payload = valid_v2_workflow()

    document = parse_workflow_dsl_document(payload)

    assert isinstance(document, WorkflowDslV2Document)
    assert document.schema_version == 2
    assert document.runtime_modes == ("historical_simulation", "live_simulation")
    assert document.edges[0].source_port == "trades"
    assert document.edges[0].target_port == "trades"
    assert canonical_workflow_json(payload) == canonical_workflow_json(deepcopy(payload))


def test_v1_document_remains_readable() -> None:
    document = parse_workflow_dsl_document(valid_v1_workflow())

    assert document.workflow_id == "visual-simulation-workflow"
    assert [node.type for node in document.nodes][-1] == "audit_sink"


def test_v2_rejects_incompatible_ports_unknown_ports_and_cycles() -> None:
    payload = valid_v2_workflow()
    payload["edges"][1]["target_port"] = "trades"
    with pytest.raises(WorkflowDslError, match="incompatible port types"):
        parse_workflow_dsl_document(payload)

    payload = valid_v2_workflow()
    payload["edges"][0]["source_port"] = "missing"
    with pytest.raises(WorkflowDslError, match="unknown source port"):
        parse_workflow_dsl_document(payload)

    payload = valid_v2_workflow()
    risk_gate_edge = next(edge for edge in payload["edges"] if edge["target_node"] == "risk-gate")
    risk_gate_edge["source_node"] = "stale-data-gate"
    risk_gate_edge["source_port"] = "plan"
    with pytest.raises(WorkflowDslError, match="cycle"):
        parse_workflow_dsl_document(payload)


@pytest.mark.parametrize(
    "removed_type",
    [
        "long_risk_size",
        "risk_gate",
        "armed_run_authorization",
        "stale_data_gate",
        "reconciliation_gate",
        "emergency_stop_gate",
        "protective_stop",
        "position_monitor",
        "audit_sink",
    ],
)
def test_v2_requires_every_safety_node_on_the_execution_path(removed_type: str) -> None:
    payload = valid_v2_workflow()
    removed_ids = {node["id"] for node in payload["nodes"] if node["type"] == removed_type}
    payload["nodes"] = [node for node in payload["nodes"] if node["id"] not in removed_ids]
    payload["edges"] = [
        edge
        for edge in payload["edges"]
        if edge["source_node"] not in removed_ids and edge["target_node"] not in removed_ids
    ]

    with pytest.raises(WorkflowDslError, match="missing required node types"):
        parse_workflow_dsl_document(payload)


def test_v2_rejects_disconnected_safety_gate_and_multiple_execution_sinks() -> None:
    payload = valid_v2_workflow()
    payload["edges"] = [
        edge
        for edge in payload["edges"]
        if not (edge["source_node"] == "risk-gate" and edge["target_node"] == "stale-data-gate")
    ]
    with pytest.raises(WorkflowDslError, match="risk-increasing execution path"):
        parse_workflow_dsl_document(payload)

    payload = valid_v2_workflow()
    payload["nodes"].append(
        {
            "id": "fake-broker-2",
            "type": "fake_broker",
            "config": {},
            "position": {"x": 2200, "y": 400},
        }
    )
    with pytest.raises(WorkflowDslError, match="exactly one execution sink"):
        parse_workflow_dsl_document(payload)


def test_v2_rejects_missing_runtime_inputs_and_unsafe_modes() -> None:
    payload = valid_v2_workflow()
    payload["runtime_inputs"] = [
        item for item in payload["runtime_inputs"] if item["key"] != "maximum_dollar_loss"
    ]
    with pytest.raises(WorkflowDslError, match="maximum_dollar_loss"):
        parse_workflow_dsl_document(payload)

    payload = valid_v2_workflow()
    payload["runtime_modes"] = ["paper"]
    with pytest.raises(WorkflowDslError, match="runtime_modes"):
        parse_workflow_dsl_document(payload)

    payload = valid_v2_workflow()
    payload["execution_target"] = "external_transport"
    with pytest.raises(WorkflowDslError, match="execution_target"):
        parse_workflow_dsl_document(payload)


def valid_v2_workflow() -> dict[str, object]:
    nodes = [
        _node("historical-data", "historical_dataset", 0, 0, {"resolution": "trade_ticks"}),
        _node("symbol", "symbol_input", 0, 160, {}),
        _node("dollar-risk", "dollar_risk_input", 0, 320, {}),
        _node("rth", "rth_session", 250, 0, {}),
        _node("opening-high", "opening_range_high", 500, 0, {"minutes": 5}),
        _node("day-low", "day_low", 500, 180, {}),
        _node("cross", "crosses_above", 750, 0, {}),
        _node("one-shot", "one_shot_per_session", 1000, 0, {}),
        _node("risk-size", "long_risk_size", 1250, 0, {}),
        _node("risk-gate", "risk_gate", 1500, 0, {}),
        _node("stale-data-gate", "stale_data_gate", 1750, 0, {}),
        _node("reconciliation-gate", "reconciliation_gate", 2000, 0, {}),
        _node("emergency-stop-gate", "emergency_stop_gate", 2250, 0, {}),
        _node("arming", "armed_run_authorization", 2500, 0, {}),
        _node("entry-lifetime", "entry_lifetime", 2750, 0, {"value": "DAY"}),
        _node(
            "position-lifetime",
            "position_lifetime",
            3000,
            0,
            {"kind": "hold_with_protective_stop"},
        ),
        _node("protective-stop", "protective_stop", 3250, 0, {"time_in_force": "GTC"}),
        _node("entry", "stop_market_entry", 3500, 0, {}),
        _node("fake-broker", "fake_broker", 3750, 0, {}),
        _node("position-monitor", "position_monitor", 4000, 0, {}),
        _node("alert", "alert", 4250, 0, {}),
        _node("audit", "audit_sink", 4500, 0, {}),
    ]
    edges = [
        _edge("historical-data", "trades", "rth", "trades"),
        _edge("symbol", "symbol", "rth", "symbol"),
        _edge("rth", "trades", "opening-high", "trades"),
        _edge("rth", "session", "opening-high", "session"),
        _edge("rth", "trades", "day-low", "trades"),
        _edge("rth", "session", "day-low", "session"),
        _edge("rth", "trades", "cross", "trades"),
        _edge("rth", "contract", "cross", "contract"),
        _edge("opening-high", "price", "cross", "level"),
        _edge("cross", "trigger", "one-shot", "trigger"),
        _edge("rth", "session", "one-shot", "session"),
        _edge("one-shot", "trigger", "risk-size", "trigger"),
        _edge("day-low", "price", "risk-size", "stop_price"),
        _edge("dollar-risk", "money", "risk-size", "maximum_dollar_loss"),
        _edge("rth", "contract", "risk-size", "contract"),
        _edge("risk-size", "plan", "risk-gate", "plan"),
        _edge("risk-gate", "plan", "stale-data-gate", "plan"),
        _edge("rth", "trades", "stale-data-gate", "trades"),
        _edge("stale-data-gate", "plan", "reconciliation-gate", "plan"),
        _edge("reconciliation-gate", "plan", "emergency-stop-gate", "plan"),
        _edge("emergency-stop-gate", "plan", "arming", "plan"),
        _edge("arming", "plan", "entry-lifetime", "plan"),
        _edge("entry-lifetime", "plan", "position-lifetime", "plan"),
        _edge("position-lifetime", "plan", "protective-stop", "plan"),
        _edge("day-low", "price", "protective-stop", "stop_price"),
        _edge("protective-stop", "plan", "entry", "plan"),
        _edge("one-shot", "trigger", "entry", "trigger"),
        _edge("entry", "plan", "fake-broker", "plan"),
        _edge("fake-broker", "report", "position-monitor", "report"),
        _edge("position-monitor", "position", "alert", "position"),
        _edge("alert", "event", "audit", "event"),
    ]
    return {
        "schema_version": 2,
        "workflow_id": "first-five-minute-breakout",
        "mode": "simulation",
        "runtime_modes": ["historical_simulation", "live_simulation"],
        "execution_target": "fake_broker",
        "instrument_scope": {
            "asset_class": "stock",
            "side": "long",
            "currency": "USD",
            "routing": "SMART",
            "session": "US_RTH",
        },
        "runtime_inputs": [
            {"key": "symbol", "data_type": "Symbol", "required": True},
            {"key": "maximum_dollar_loss", "data_type": "Money", "required": True},
        ],
        "nodes": nodes,
        "edges": edges,
        "safety_gates": {
            "risk_check_required": True,
            "armed_authorization_required": True,
            "protective_stop_required": True,
            "stale_data_required": True,
            "reconciliation_required": True,
            "emergency_stop_required": True,
            "position_monitor_required": True,
            "audit_sink_required": True,
            "broker_transport_allowed": False,
            "live_trading_enabled": False,
            "arbitrary_code_allowed": False,
        },
    }


def valid_v1_workflow() -> dict[str, object]:
    node_types = [
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
    nodes = [
        {
            "id": node_type.replace("_", "-"),
            "type": node_type,
            "required_for_risk_increasing_path": True,
        }
        for node_type in node_types
    ]
    return {
        "schema_version": 1,
        "workflow_id": "visual-simulation-workflow",
        "mode": "simulation",
        "runtime": "preview_only",
        "broker": "fake_broker_only",
        "nodes": nodes,
        "edges": [
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"]}
            for index in range(len(nodes) - 1)
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


def _node(
    node_id: str,
    node_type: str,
    x: int,
    y: int,
    config: dict[str, object],
) -> dict[str, object]:
    return {
        "id": node_id,
        "type": node_type,
        "config": config,
        "position": {"x": x, "y": y},
    }


def _edge(
    source_node: str,
    source_port: str,
    target_node: str,
    target_port: str,
) -> dict[str, str]:
    return {
        "id": f"{source_node}.{source_port}-to-{target_node}.{target_port}",
        "source_node": source_node,
        "source_port": source_port,
        "target_node": target_node,
        "target_port": target_port,
    }
