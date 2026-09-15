from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal


class WorkflowDslError(ValueError):
    """Raised when a visual workflow DSL document is unsafe or invalid."""


ALLOWED_WORKFLOW_NODE_TYPES = {
    "replay_source",
    "bar_builder",
    "strategy_trigger",
    "risk_check",
    "approval_ticket",
    "fake_broker",
    "position_update",
    "alert",
    "audit_sink",
}

REQUIRED_WORKFLOW_NODE_TYPES = {
    "risk_check",
    "approval_ticket",
    "audit_sink",
}

FORBIDDEN_WORKFLOW_TOKENS = (
    "account",
    "api_key",
    "broker_host",
    "credential",
    "eval",
    "ibkr",
    "import",
    "javascript",
    "live_mode",
    "password",
    "route",
    "script",
    "secret",
    "submit",
    "token",
    "transmit",
)

WORKFLOW_V2_RUNTIME_MODES = ("historical_simulation", "live_simulation")
WORKFLOW_V2_EXECUTION_TARGET = "fake_broker"
WORKFLOW_V2_PORT_TYPES = (
    "TradeStream",
    "Session",
    "Symbol",
    "Contract",
    "Price",
    "Money",
    "TriggerEvent",
    "OrderPlan",
    "AuthorizedOrderPlan",
    "ProtectedOrderPlan",
    "ExecutionReport",
    "PositionState",
    "AuditEvent",
)


@dataclass(frozen=True)
class WorkflowNodeSpec:
    type: str
    label: str
    category: str
    inputs: Mapping[str, str]
    outputs: Mapping[str, str]
    default_config: Mapping[str, Any]
    execution_capability: Literal["none", "simulation_only"] = "none"

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "category": self.category,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "default_config": _json_copy(self.default_config),
            "execution_capability": self.execution_capability,
        }


def _spec(
    node_type: str,
    label: str,
    category: str,
    *,
    inputs: Mapping[str, str] | None = None,
    outputs: Mapping[str, str] | None = None,
    default_config: Mapping[str, Any] | None = None,
    execution_capability: Literal["none", "simulation_only"] = "none",
) -> WorkflowNodeSpec:
    return WorkflowNodeSpec(
        type=node_type,
        label=label,
        category=category,
        inputs={} if inputs is None else inputs,
        outputs={} if outputs is None else outputs,
        default_config={} if default_config is None else default_config,
        execution_capability=execution_capability,
    )


WORKFLOW_V2_NODE_SPECS = (
    _spec(
        "historical_dataset",
        "Historical dataset",
        "inputs",
        outputs={"trades": "TradeStream"},
        default_config={"resolution": "trade_ticks"},
    ),
    _spec("live_trades", "Live trades", "inputs", outputs={"trades": "TradeStream"}),
    _spec("symbol_input", "Symbol", "inputs", outputs={"symbol": "Symbol"}),
    _spec("dollar_risk_input", "Dollar risk", "inputs", outputs={"money": "Money"}),
    _spec(
        "rth_session",
        "US regular session",
        "session_metrics",
        inputs={"trades": "TradeStream", "symbol": "Symbol"},
        outputs={"trades": "TradeStream", "session": "Session", "contract": "Contract"},
    ),
    _spec(
        "opening_range_high",
        "Opening-range high",
        "session_metrics",
        inputs={"trades": "TradeStream", "session": "Session"},
        outputs={"price": "Price"},
        default_config={"minutes": 5},
    ),
    _spec(
        "opening_range_low",
        "Opening-range low",
        "session_metrics",
        inputs={"trades": "TradeStream", "session": "Session"},
        outputs={"price": "Price"},
        default_config={"minutes": 5},
    ),
    _spec(
        "day_high",
        "Day high",
        "session_metrics",
        inputs={"trades": "TradeStream", "session": "Session"},
        outputs={"price": "Price"},
    ),
    _spec(
        "day_low",
        "Day low",
        "session_metrics",
        inputs={"trades": "TradeStream", "session": "Session"},
        outputs={"price": "Price"},
    ),
    _spec(
        "crosses_above",
        "Crosses above",
        "logic",
        inputs={"trades": "TradeStream", "level": "Price", "contract": "Contract"},
        outputs={"trigger": "TriggerEvent"},
    ),
    _spec(
        "crosses_below",
        "Crosses below",
        "logic",
        inputs={"trades": "TradeStream", "level": "Price", "contract": "Contract"},
        outputs={"trigger": "TriggerEvent"},
    ),
    _spec(
        "one_shot_per_session",
        "One shot per session",
        "logic",
        inputs={"trigger": "TriggerEvent", "session": "Session"},
        outputs={"trigger": "TriggerEvent"},
    ),
    _spec(
        "long_risk_size",
        "Long dollar-risk sizing",
        "sizing",
        inputs={
            "trigger": "TriggerEvent",
            "stop_price": "Price",
            "maximum_dollar_loss": "Money",
            "contract": "Contract",
        },
        outputs={"plan": "OrderPlan"},
    ),
    _spec(
        "risk_gate",
        "Risk gate",
        "safety",
        inputs={"plan": "OrderPlan"},
        outputs={"plan": "OrderPlan"},
    ),
    _spec(
        "stale_data_gate",
        "Stale-data gate",
        "safety",
        inputs={"plan": "OrderPlan", "trades": "TradeStream"},
        outputs={"plan": "OrderPlan"},
    ),
    _spec(
        "reconciliation_gate",
        "Reconciliation gate",
        "safety",
        inputs={"plan": "OrderPlan"},
        outputs={"plan": "OrderPlan"},
    ),
    _spec(
        "emergency_stop_gate",
        "Emergency-stop gate",
        "safety",
        inputs={"plan": "OrderPlan"},
        outputs={"plan": "OrderPlan"},
    ),
    _spec(
        "armed_run_authorization",
        "Armed-run authorization",
        "safety",
        inputs={"plan": "OrderPlan"},
        outputs={"plan": "AuthorizedOrderPlan"},
    ),
    _spec(
        "entry_lifetime",
        "Entry lifetime",
        "orders",
        inputs={"plan": "AuthorizedOrderPlan"},
        outputs={"plan": "AuthorizedOrderPlan"},
        default_config={"value": "DAY"},
    ),
    _spec(
        "position_lifetime",
        "Position lifetime",
        "orders",
        inputs={"plan": "AuthorizedOrderPlan"},
        outputs={"plan": "AuthorizedOrderPlan"},
        default_config={"kind": "hold_with_protective_stop"},
    ),
    _spec(
        "protective_stop",
        "Protective stop",
        "orders",
        inputs={"plan": "AuthorizedOrderPlan", "stop_price": "Price"},
        outputs={"plan": "ProtectedOrderPlan"},
        default_config={"time_in_force": "GTC"},
    ),
    _spec(
        "stop_market_entry",
        "Stop-market entry",
        "orders",
        inputs={"plan": "ProtectedOrderPlan", "trigger": "TriggerEvent"},
        outputs={"plan": "ProtectedOrderPlan"},
    ),
    _spec(
        "fake_broker",
        "Fake broker",
        "execution",
        inputs={"plan": "ProtectedOrderPlan"},
        outputs={"report": "ExecutionReport"},
        execution_capability="simulation_only",
    ),
    _spec(
        "position_monitor",
        "Position monitor",
        "monitoring",
        inputs={"report": "ExecutionReport"},
        outputs={"position": "PositionState"},
    ),
    _spec(
        "alert",
        "Alerts",
        "monitoring",
        inputs={"position": "PositionState"},
        outputs={"event": "AuditEvent"},
    ),
    _spec(
        "audit_sink",
        "Audit sink",
        "monitoring",
        inputs={"event": "AuditEvent"},
    ),
)

WORKFLOW_V2_NODE_SPEC_BY_TYPE = {spec.type: spec for spec in WORKFLOW_V2_NODE_SPECS}

WORKFLOW_V2_REQUIRED_NODE_TYPES = {
    "historical_dataset",
    "symbol_input",
    "dollar_risk_input",
    "rth_session",
    "opening_range_high",
    "day_low",
    "crosses_above",
    "one_shot_per_session",
    "long_risk_size",
    "risk_gate",
    "stale_data_gate",
    "reconciliation_gate",
    "emergency_stop_gate",
    "armed_run_authorization",
    "entry_lifetime",
    "position_lifetime",
    "protective_stop",
    "stop_market_entry",
    "fake_broker",
    "position_monitor",
    "alert",
    "audit_sink",
}

WORKFLOW_V2_UPSTREAM_SAFETY_TYPES = {
    "long_risk_size",
    "risk_gate",
    "stale_data_gate",
    "reconciliation_gate",
    "emergency_stop_gate",
    "armed_run_authorization",
    "entry_lifetime",
    "position_lifetime",
    "protective_stop",
    "stop_market_entry",
}

WORKFLOW_V2_DOWNSTREAM_SAFETY_TYPES = {"position_monitor", "alert", "audit_sink"}

WORKFLOW_V2_SAFETY_GATES = {
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
}


@dataclass(frozen=True)
class WorkflowDslNode:
    id: str
    type: str
    required_for_risk_increasing_path: bool


@dataclass(frozen=True)
class WorkflowDslEdge:
    source: str
    target: str


@dataclass(frozen=True)
class WorkflowDslDocument:
    workflow_id: str
    nodes: tuple[WorkflowDslNode, ...]
    edges: tuple[WorkflowDslEdge, ...]


@dataclass(frozen=True)
class WorkflowDslV2Node:
    id: str
    type: str
    config: Mapping[str, Any]
    position_x: float
    position_y: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "config": _json_copy(self.config),
            "position": {"x": self.position_x, "y": self.position_y},
        }


@dataclass(frozen=True)
class WorkflowDslV2Edge:
    id: str
    source_node: str
    source_port: str
    target_node: str
    target_port: str

    def to_payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "source_node": self.source_node,
            "source_port": self.source_port,
            "target_node": self.target_node,
            "target_port": self.target_port,
        }


@dataclass(frozen=True)
class WorkflowRuntimeInput:
    key: str
    data_type: str
    required: bool

    def to_payload(self) -> dict[str, Any]:
        return {"key": self.key, "data_type": self.data_type, "required": self.required}


@dataclass(frozen=True)
class WorkflowDslV2Document:
    workflow_id: str
    runtime_modes: tuple[str, ...]
    runtime_inputs: tuple[WorkflowRuntimeInput, ...]
    nodes: tuple[WorkflowDslV2Node, ...]
    edges: tuple[WorkflowDslV2Edge, ...]
    schema_version: int = 2

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "workflow_id": self.workflow_id,
            "mode": "simulation",
            "runtime_modes": list(self.runtime_modes),
            "execution_target": WORKFLOW_V2_EXECUTION_TARGET,
            "instrument_scope": {
                "asset_class": "stock",
                "side": "long",
                "currency": "USD",
                "routing": "SMART",
                "session": "US_RTH",
            },
            "runtime_inputs": [item.to_payload() for item in self.runtime_inputs],
            "nodes": [node.to_payload() for node in self.nodes],
            "edges": [edge.to_payload() for edge in self.edges],
            "safety_gates": dict(WORKFLOW_V2_SAFETY_GATES),
        }


type ParsedWorkflowDocument = WorkflowDslDocument | WorkflowDslV2Document


def workflow_node_catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "port_types": list(WORKFLOW_V2_PORT_TYPES),
        "nodes": [spec.to_payload() for spec in WORKFLOW_V2_NODE_SPECS],
        "execution_targets": [WORKFLOW_V2_EXECUTION_TARGET],
        "runtime_modes": list(WORKFLOW_V2_RUNTIME_MODES),
    }


def canonical_workflow_json(payload: Mapping[str, Any]) -> str:
    document = parse_workflow_dsl_document(payload)
    normalized: Mapping[str, Any]
    if isinstance(document, WorkflowDslV2Document):
        normalized = document.to_payload()
    else:
        normalized = _json_copy(payload)
    return json.dumps(normalized, allow_nan=False, separators=(",", ":"), sort_keys=True)


def parse_workflow_dsl_document(payload: Mapping[str, Any]) -> ParsedWorkflowDocument:
    if not isinstance(payload, Mapping):
        raise WorkflowDslError("workflow must be an object")
    schema_version = payload.get("schema_version")
    if schema_version == 1:
        return _parse_workflow_dsl_v1(payload)
    if schema_version == 2:
        return _parse_workflow_dsl_v2(payload)
    raise WorkflowDslError("schema_version must be 1 or 2")


def _parse_workflow_dsl_v1(payload: Mapping[str, Any]) -> WorkflowDslDocument:
    _reject_forbidden_content(payload, "workflow")

    if payload.get("workflow_id") != "visual-simulation-workflow":
        raise WorkflowDslError("workflow_id must be visual-simulation-workflow")
    if payload.get("mode") != "simulation":
        raise WorkflowDslError("workflow mode must be simulation")
    if payload.get("runtime") != "preview_only":
        raise WorkflowDslError("workflow runtime must be preview_only")
    if payload.get("broker") != "fake_broker_only":
        raise WorkflowDslError("workflow broker must be fake_broker_only")

    safety_gates = _require_mapping(payload.get("safety_gates"), "safety_gates")
    expected_safety_gates = {
        "risk_check_required": True,
        "manual_approval_required": True,
        "audit_sink_required": True,
        "broker_transport_allowed": False,
        "live_trading_enabled": False,
        "arbitrary_code_allowed": False,
    }
    for key, expected_value in expected_safety_gates.items():
        if safety_gates.get(key) is not expected_value:
            raise WorkflowDslError(f"safety_gates.{key} must be {expected_value!r}")

    nodes = tuple(_parse_v1_node(item) for item in _require_list(payload.get("nodes"), "nodes"))
    edges = tuple(_parse_v1_edge(item) for item in _require_list(payload.get("edges"), "edges"))

    _validate_v1_node_types(nodes)
    _validate_v1_edges(nodes, edges)

    return WorkflowDslDocument(
        workflow_id="visual-simulation-workflow",
        nodes=nodes,
        edges=edges,
    )


def _parse_workflow_dsl_v2(payload: Mapping[str, Any]) -> WorkflowDslV2Document:
    _reject_forbidden_content(payload, "workflow")
    _require_exact_fields(
        payload,
        {
            "schema_version",
            "workflow_id",
            "mode",
            "runtime_modes",
            "execution_target",
            "instrument_scope",
            "runtime_inputs",
            "nodes",
            "edges",
            "safety_gates",
        },
        "workflow",
    )
    workflow_id = _require_safe_string(payload.get("workflow_id"), "workflow_id")
    if payload.get("mode") != "simulation":
        raise WorkflowDslError("workflow mode must be simulation")
    runtime_modes = tuple(_require_list(payload.get("runtime_modes"), "runtime_modes"))
    if (
        not runtime_modes
        or len(runtime_modes) != len(set(runtime_modes))
        or any(mode not in WORKFLOW_V2_RUNTIME_MODES for mode in runtime_modes)
    ):
        raise WorkflowDslError("runtime_modes must contain supported simulation modes only")
    if payload.get("execution_target") != WORKFLOW_V2_EXECUTION_TARGET:
        raise WorkflowDslError("execution_target must be fake_broker")
    _validate_instrument_scope(payload.get("instrument_scope"))
    _validate_v2_safety_gates(payload.get("safety_gates"))

    runtime_inputs = tuple(
        _parse_runtime_input(item)
        for item in _require_list(payload.get("runtime_inputs"), "runtime_inputs")
    )
    _validate_runtime_inputs(runtime_inputs)
    nodes = tuple(_parse_v2_node(item) for item in _require_list(payload.get("nodes"), "nodes"))
    edges = tuple(_parse_v2_edge(item) for item in _require_list(payload.get("edges"), "edges"))
    _validate_v2_graph(nodes, edges)

    return WorkflowDslV2Document(
        workflow_id=workflow_id,
        runtime_modes=runtime_modes,
        runtime_inputs=runtime_inputs,
        nodes=nodes,
        edges=edges,
    )


def _parse_v1_node(value: Any) -> WorkflowDslNode:
    item = _require_mapping(value, "node")
    node_id = _require_safe_string(item.get("id"), "node.id")
    node_type = _require_safe_string(item.get("type"), "node.type")
    required = item.get("required_for_risk_increasing_path")
    if required is not True:
        raise WorkflowDslError("node.required_for_risk_increasing_path must be true")
    return WorkflowDslNode(
        id=node_id,
        type=node_type,
        required_for_risk_increasing_path=True,
    )


def _parse_v1_edge(value: Any) -> WorkflowDslEdge:
    item = _require_mapping(value, "edge")
    return WorkflowDslEdge(
        source=_require_safe_string(item.get("source"), "edge.source"),
        target=_require_safe_string(item.get("target"), "edge.target"),
    )


def _parse_v2_node(value: Any) -> WorkflowDslV2Node:
    item = _require_mapping(value, "node")
    _require_exact_fields(item, {"id", "type", "config", "position"}, "node")
    node_id = _require_safe_string(item.get("id"), "node.id")
    node_type = _require_safe_string(item.get("type"), "node.type")
    spec = WORKFLOW_V2_NODE_SPEC_BY_TYPE.get(node_type)
    if spec is None:
        raise WorkflowDslError(f"unsupported node types: {node_type}")
    config = _require_mapping(item.get("config"), f"node {node_id}.config")
    _validate_node_config(node_type, config)
    position = _require_mapping(item.get("position"), f"node {node_id}.position")
    _require_exact_fields(position, {"x", "y"}, f"node {node_id}.position")
    return WorkflowDslV2Node(
        id=node_id,
        type=node_type,
        config=_json_copy(config),
        position_x=_finite_number(position.get("x"), f"node {node_id}.position.x"),
        position_y=_finite_number(position.get("y"), f"node {node_id}.position.y"),
    )


def _parse_v2_edge(value: Any) -> WorkflowDslV2Edge:
    item = _require_mapping(value, "edge")
    _require_exact_fields(
        item,
        {"id", "source_node", "source_port", "target_node", "target_port"},
        "edge",
    )
    return WorkflowDslV2Edge(
        id=_require_safe_string(item.get("id"), "edge.id"),
        source_node=_require_safe_string(item.get("source_node"), "edge.source_node"),
        source_port=_require_safe_string(item.get("source_port"), "edge.source_port"),
        target_node=_require_safe_string(item.get("target_node"), "edge.target_node"),
        target_port=_require_safe_string(item.get("target_port"), "edge.target_port"),
    )


def _parse_runtime_input(value: Any) -> WorkflowRuntimeInput:
    item = _require_mapping(value, "runtime input")
    _require_exact_fields(item, {"key", "data_type", "required"}, "runtime input")
    key = _require_safe_string(item.get("key"), "runtime_input.key")
    data_type = _require_safe_string(item.get("data_type"), "runtime_input.data_type")
    if data_type not in WORKFLOW_V2_PORT_TYPES:
        raise WorkflowDslError(f"runtime input {key} has unsupported data_type")
    if item.get("required") is not True:
        raise WorkflowDslError(f"runtime input {key} must be required")
    return WorkflowRuntimeInput(key=key, data_type=data_type, required=True)


def _validate_runtime_inputs(runtime_inputs: tuple[WorkflowRuntimeInput, ...]) -> None:
    keys = [item.key for item in runtime_inputs]
    if len(keys) != len(set(keys)):
        raise WorkflowDslError("runtime_inputs must have unique keys")
    expected = {"symbol": "Symbol", "maximum_dollar_loss": "Money"}
    actual = {item.key: item.data_type for item in runtime_inputs}
    for key, data_type in expected.items():
        if actual.get(key) != data_type:
            raise WorkflowDslError(f"runtime_inputs must declare required {key} as {data_type}")


def _validate_instrument_scope(value: Any) -> None:
    scope = _require_mapping(value, "instrument_scope")
    expected = {
        "asset_class": "stock",
        "side": "long",
        "currency": "USD",
        "routing": "SMART",
        "session": "US_RTH",
    }
    _require_exact_fields(scope, set(expected), "instrument_scope")
    if dict(scope) != expected:
        raise WorkflowDslError("instrument_scope must be long SMART-routed USD US stocks in RTH")


def _validate_v2_safety_gates(value: Any) -> None:
    safety_gates = _require_mapping(value, "safety_gates")
    _require_exact_fields(safety_gates, set(WORKFLOW_V2_SAFETY_GATES), "safety_gates")
    for key, expected in WORKFLOW_V2_SAFETY_GATES.items():
        if safety_gates.get(key) is not expected:
            raise WorkflowDslError(f"safety_gates.{key} must be {expected!r}")


def _validate_node_config(node_type: str, config: Mapping[str, Any]) -> None:
    if node_type == "historical_dataset":
        _require_exact_fields(config, {"resolution"}, f"{node_type}.config")
        if config.get("resolution") not in {"trade_ticks", "five_second_bars"}:
            raise WorkflowDslError("historical_dataset resolution is unsupported")
        return
    if node_type in {"opening_range_high", "opening_range_low"}:
        _require_exact_fields(config, {"minutes"}, f"{node_type}.config")
        minutes = config.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 60:
            raise WorkflowDslError(f"{node_type}.config.minutes must be between 1 and 60")
        return
    if node_type == "entry_lifetime":
        _require_exact_fields(config, {"value"}, f"{node_type}.config")
        if config.get("value") not in {"DAY", "GTC"}:
            raise WorkflowDslError("entry_lifetime.config.value must be DAY or GTC")
        return
    if node_type == "position_lifetime":
        kind = config.get("kind")
        if kind == "hold_with_protective_stop":
            _require_exact_fields(config, {"kind"}, f"{node_type}.config")
            return
        if kind == "exit_at_time":
            _require_exact_fields(config, {"kind", "time"}, f"{node_type}.config")
            _validated_clock_time(config.get("time"), "position_lifetime.config.time")
            return
        if kind == "exit_on_typed_condition":
            _require_exact_fields(config, {"kind"}, f"{node_type}.config")
            return
        raise WorkflowDslError("position_lifetime.config.kind is unsupported")
    if node_type == "protective_stop":
        _require_exact_fields(config, {"time_in_force"}, f"{node_type}.config")
        if config.get("time_in_force") != "GTC":
            raise WorkflowDslError("protective_stop.config.time_in_force must be GTC")
        return
    if config:
        raise WorkflowDslError(f"{node_type}.config does not accept fields")


def _validate_v1_node_types(nodes: tuple[WorkflowDslNode, ...]) -> None:
    node_types = {node.type for node in nodes}
    missing_required = sorted(REQUIRED_WORKFLOW_NODE_TYPES - node_types)
    if missing_required:
        raise WorkflowDslError(f"missing required node types: {', '.join(missing_required)}")

    unsupported = sorted(node_types - ALLOWED_WORKFLOW_NODE_TYPES)
    if unsupported:
        raise WorkflowDslError(f"unsupported node types: {', '.join(unsupported)}")


def _validate_v1_edges(
    nodes: tuple[WorkflowDslNode, ...], edges: tuple[WorkflowDslEdge, ...]
) -> None:
    node_ids = {node.id for node in nodes}
    for edge in edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise WorkflowDslError(f"edge {edge.source}->{edge.target} references an unknown node")

    if _has_cycle(node_ids, tuple((edge.source, edge.target) for edge in edges)):
        raise WorkflowDslError("workflow graph contains a cycle")


def _validate_v2_graph(
    nodes: tuple[WorkflowDslV2Node, ...], edges: tuple[WorkflowDslV2Edge, ...]
) -> None:
    node_ids = [node.id for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise WorkflowDslError("workflow node ids must be unique")
    edge_ids = [edge.id for edge in edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise WorkflowDslError("workflow edge ids must be unique")

    node_types = {node.type for node in nodes}
    missing = sorted(WORKFLOW_V2_REQUIRED_NODE_TYPES - node_types)
    if missing:
        raise WorkflowDslError(f"missing required node types: {', '.join(missing)}")

    execution_nodes = [node for node in nodes if node.type == "fake_broker"]
    if len(execution_nodes) != 1:
        raise WorkflowDslError("workflow must contain exactly one execution sink")

    by_id = {node.id: node for node in nodes}
    occupied_inputs: set[tuple[str, str]] = set()
    edge_pairs: list[tuple[str, str]] = []
    for edge in edges:
        source = by_id.get(edge.source_node)
        target = by_id.get(edge.target_node)
        if source is None or target is None:
            raise WorkflowDslError(f"edge {edge.id} references an unknown node")
        source_spec = WORKFLOW_V2_NODE_SPEC_BY_TYPE[source.type]
        target_spec = WORKFLOW_V2_NODE_SPEC_BY_TYPE[target.type]
        source_type = source_spec.outputs.get(edge.source_port)
        if source_type is None:
            raise WorkflowDslError(f"edge {edge.id} references an unknown source port")
        target_type = target_spec.inputs.get(edge.target_port)
        if target_type is None:
            raise WorkflowDslError(f"edge {edge.id} references an unknown target port")
        if source_type != target_type:
            raise WorkflowDslError(
                f"edge {edge.id} has incompatible port types {source_type}->{target_type}"
            )
        input_key = (edge.target_node, edge.target_port)
        if input_key in occupied_inputs:
            raise WorkflowDslError(
                f"node {edge.target_node} input port {edge.target_port} has multiple connections"
            )
        occupied_inputs.add(input_key)
        edge_pairs.append((edge.source_node, edge.target_node))

    node_id_set = set(node_ids)
    if _has_cycle(node_id_set, tuple(edge_pairs)):
        raise WorkflowDslError("workflow graph contains a cycle")

    execution_id = execution_nodes[0].id
    ancestors = _reachable(execution_id, edge_pairs, reverse=True)
    descendants = _reachable(execution_id, edge_pairs, reverse=False)
    ancestor_types = {by_id[node_id].type for node_id in ancestors}
    descendant_types = {by_id[node_id].type for node_id in descendants}
    if not WORKFLOW_V2_UPSTREAM_SAFETY_TYPES.issubset(ancestor_types):
        raise WorkflowDslError(
            "every required safety node must be on the risk-increasing execution path"
        )
    if not WORKFLOW_V2_DOWNSTREAM_SAFETY_TYPES.issubset(descendant_types):
        raise WorkflowDslError(
            "position monitoring, alerts, and audit must follow the execution path"
        )

    for node in nodes:
        spec = WORKFLOW_V2_NODE_SPEC_BY_TYPE[node.type]
        for input_name in spec.inputs:
            if (node.id, input_name) not in occupied_inputs:
                raise WorkflowDslError(
                    f"node {node.id} required input {input_name} is not connected"
                )

    _validate_supported_breakout(nodes, edges)


def _reachable(start: str, pairs: list[tuple[str, str]], *, reverse: bool) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for source, target in pairs:
        origin, destination = (target, source) if reverse else (source, target)
        adjacency.setdefault(origin, []).append(destination)
    seen: set[str] = set()
    pending = list(adjacency.get(start, ()))
    while pending:
        node_id = pending.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        pending.extend(adjacency.get(node_id, ()))
    return seen


def _has_cycle(node_ids: set[str], edges: tuple[tuple[str, str], ...]) -> bool:
    outgoing = {node_id: [] for node_id in node_ids}
    for source, target in edges:
        outgoing[source].append(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False

        visiting.add(node_id)
        for target in outgoing[node_id]:
            if visit(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in node_ids)


def _validated_clock_time(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise WorkflowDslError(f"{field_name} must be HH:MM:SS")
    parts = value.split(":")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise WorkflowDslError(f"{field_name} must be HH:MM:SS")
    hour, minute, second = (int(part) for part in parts)
    if hour > 23 or minute > 59 or second > 59:
        raise WorkflowDslError(f"{field_name} must be HH:MM:SS")
    return value


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkflowDslError(f"{field_name} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise WorkflowDslError(f"{field_name} must be a finite number")
    return converted


def _require_exact_fields(
    value: Mapping[str, Any], expected_fields: set[str], object_name: str
) -> None:
    actual_fields = set(value)
    missing = sorted(expected_fields - actual_fields)
    unknown = sorted(actual_fields - expected_fields)
    if missing:
        raise WorkflowDslError(f"{object_name} is missing field {missing[0]}")
    if unknown:
        raise WorkflowDslError(f"{object_name} contains unknown field {unknown[0]}")


def _require_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise WorkflowDslError(f"{field_name} must be a list")
    return value


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowDslError(f"{field_name} must be an object")
    return value


def _require_safe_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowDslError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise WorkflowDslError(f"{field_name} must not contain surrounding whitespace")
    _reject_forbidden_text(value, field_name)
    return value


def _reject_forbidden_content(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _reject_forbidden_text(str(key), field_name)
            _reject_forbidden_content(nested, field_name)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_content(item, field_name)
    elif isinstance(value, str):
        _reject_forbidden_text(value, field_name)


def _reject_forbidden_text(value: str, field_name: str) -> None:
    normalized = value.lower().replace("-", "_")
    for token in FORBIDDEN_WORKFLOW_TOKENS:
        if token in normalized:
            raise WorkflowDslError(f"{field_name} contains forbidden workflow token {token}")


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise WorkflowDslError("workflow content must be JSON-serializable") from exc


SUPPORTED_BREAKOUT_EDGES = frozenset(
    (
        ("alert", "event", "audit_sink", "event"),
        ("armed_run_authorization", "plan", "entry_lifetime", "plan"),
        ("crosses_above", "trigger", "one_shot_per_session", "trigger"),
        ("day_low", "price", "long_risk_size", "stop_price"),
        ("day_low", "price", "protective_stop", "stop_price"),
        ("dollar_risk_input", "money", "long_risk_size", "maximum_dollar_loss"),
        ("emergency_stop_gate", "plan", "armed_run_authorization", "plan"),
        ("entry_lifetime", "plan", "position_lifetime", "plan"),
        ("fake_broker", "report", "position_monitor", "report"),
        ("historical_dataset", "trades", "rth_session", "trades"),
        ("long_risk_size", "plan", "risk_gate", "plan"),
        ("one_shot_per_session", "trigger", "long_risk_size", "trigger"),
        ("one_shot_per_session", "trigger", "stop_market_entry", "trigger"),
        ("opening_range_high", "price", "crosses_above", "level"),
        ("position_lifetime", "plan", "protective_stop", "plan"),
        ("position_monitor", "position", "alert", "position"),
        ("protective_stop", "plan", "stop_market_entry", "plan"),
        ("reconciliation_gate", "plan", "emergency_stop_gate", "plan"),
        ("risk_gate", "plan", "stale_data_gate", "plan"),
        ("rth_session", "contract", "crosses_above", "contract"),
        ("rth_session", "contract", "long_risk_size", "contract"),
        ("rth_session", "session", "day_low", "session"),
        ("rth_session", "session", "one_shot_per_session", "session"),
        ("rth_session", "session", "opening_range_high", "session"),
        ("rth_session", "trades", "crosses_above", "trades"),
        ("rth_session", "trades", "day_low", "trades"),
        ("rth_session", "trades", "opening_range_high", "trades"),
        ("rth_session", "trades", "stale_data_gate", "trades"),
        ("stale_data_gate", "plan", "reconciliation_gate", "plan"),
        ("stop_market_entry", "plan", "fake_broker", "plan"),
        ("symbol_input", "symbol", "rth_session", "symbol"),
    )
)


def _validate_supported_breakout(nodes, edges) -> None:
    by_id = {node.id: node.type for node in nodes}
    required = {edge[0] for edge in SUPPORTED_BREAKOUT_EDGES} | {
        edge[2] for edge in SUPPORTED_BREAKOUT_EDGES
    }
    actual = {
        (by_id[e.source_node], e.source_port, by_id[e.target_node], e.target_port) for e in edges
    }
    if (
        len(nodes) != len(required)
        or set(by_id.values()) != required
        or len(edges) != len(SUPPORTED_BREAKOUT_EDGES)
        or actual != SUPPORTED_BREAKOUT_EDGES
    ):
        raise WorkflowDslError("workflow must use the supported breakout topology")
