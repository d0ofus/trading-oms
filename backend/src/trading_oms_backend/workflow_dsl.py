from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


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


def parse_workflow_dsl_document(payload: Mapping[str, Any]) -> WorkflowDslDocument:
    _reject_forbidden_content(payload, "workflow")

    if payload.get("schema_version") != 1:
        raise WorkflowDslError("schema_version must be 1")
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

    nodes = tuple(_parse_node(item) for item in _require_list(payload.get("nodes"), "nodes"))
    edges = tuple(_parse_edge(item) for item in _require_list(payload.get("edges"), "edges"))

    _validate_node_types(nodes)
    _validate_edges(nodes, edges)

    return WorkflowDslDocument(
        workflow_id="visual-simulation-workflow",
        nodes=nodes,
        edges=edges,
    )


def _parse_node(value: Any) -> WorkflowDslNode:
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


def _parse_edge(value: Any) -> WorkflowDslEdge:
    item = _require_mapping(value, "edge")
    return WorkflowDslEdge(
        source=_require_safe_string(item.get("source"), "edge.source"),
        target=_require_safe_string(item.get("target"), "edge.target"),
    )


def _validate_node_types(nodes: tuple[WorkflowDslNode, ...]) -> None:
    node_types = {node.type for node in nodes}
    missing_required = sorted(REQUIRED_WORKFLOW_NODE_TYPES - node_types)
    if missing_required:
        raise WorkflowDslError(f"missing required node types: {', '.join(missing_required)}")

    unsupported = sorted(node_types - ALLOWED_WORKFLOW_NODE_TYPES)
    if unsupported:
        raise WorkflowDslError(f"unsupported node types: {', '.join(unsupported)}")


def _validate_edges(nodes: tuple[WorkflowDslNode, ...], edges: tuple[WorkflowDslEdge, ...]) -> None:
    node_ids = {node.id for node in nodes}
    for edge in edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise WorkflowDslError(f"edge {edge.source}->{edge.target} references an unknown node")

    if _has_cycle(node_ids, edges):
        raise WorkflowDslError("workflow graph contains a cycle")


def _has_cycle(node_ids: set[str], edges: tuple[WorkflowDslEdge, ...]) -> bool:
    outgoing = {node_id: [] for node_id in node_ids}
    for edge in edges:
        outgoing[edge.source].append(edge.target)

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
