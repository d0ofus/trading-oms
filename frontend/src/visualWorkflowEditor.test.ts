import { describe, expect, it } from "vitest";

import type { VisualWorkflowNodeType } from "./visualWorkflowNodeCatalog";
import {
  addVisualWorkflowNode,
  connectVisualWorkflowNodes,
  createInitialVisualWorkflowEditorState,
  moveVisualWorkflowNode,
  removeSelectedVisualWorkflowElement,
  removeVisualWorkflowEdge,
  removeVisualWorkflowNode,
  resetVisualWorkflowEditorState,
  selectVisualWorkflowElement,
} from "./visualWorkflowEditor";

describe("visualWorkflowEditor", () => {
  it("creates independent deterministic state from the typed safe catalog", () => {
    const first = createInitialVisualWorkflowEditorState();
    const second = createInitialVisualWorkflowEditorState();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first.nodes).not.toBe(second.nodes);
    expect(first.nodes[0].position).not.toBe(second.nodes[0].position);
    expect(first.nodes.map((node) => node.type)).toEqual([
      "replay_source",
      "bar_builder",
      "strategy_trigger",
      "risk_check",
      "approval_ticket",
      "fake_broker",
      "position_update",
      "alert",
      "audit_sink",
    ]);
    expect(first.edges.every((edge) => edge.type === "workflow")).toBe(true);
    expect(first.selection).toBeNull();

    const serialized = JSON.stringify(first).toLowerCase();
    for (const forbidden of [
      "account_id",
      "api_key",
      "broker_host",
      "credential",
      "ibkr",
      "live_mode",
      "password",
      "place_order",
      "script",
      "secret",
      "submit_order",
      "token",
      "transmit_order",
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("removes and restores typed nodes while preventing duplicate or unsupported nodes", () => {
    const initial = createInitialVisualWorkflowEditorState();
    const removed = removeVisualWorkflowNode(initial, "alert");

    expect(removed.changed).toBe(true);
    expect(removed.state.nodes.some((node) => node.id === "alert")).toBe(false);
    expect(
      removed.state.edges.some((edge) => edge.source === "alert" || edge.target === "alert"),
    ).toBe(false);

    const restored = addVisualWorkflowNode(removed.state, "alert");
    expect(restored.changed).toBe(true);
    expect(restored.reason).toBeNull();
    expect(restored.state.nodes.filter((node) => node.type === "alert")).toHaveLength(1);
    expect(restored.state.selection).toEqual({ kind: "node", id: "alert" });

    const duplicate = addVisualWorkflowNode(restored.state, "alert");
    expect(duplicate.changed).toBe(false);
    expect(duplicate.reason).toBe("duplicate_node");
    expect(duplicate.state).toBe(restored.state);

    const unsupported = addVisualWorkflowNode(
      restored.state,
      "unsupported_node" as VisualWorkflowNodeType,
    );
    expect(unsupported.changed).toBe(false);
    expect(unsupported.reason).toBe("unsupported_node_type");
    expect(unsupported.state).toBe(restored.state);
  });

  it("selects, moves, and removes a node through the shared cleanup path", () => {
    const initial = createInitialVisualWorkflowEditorState();
    const selected = selectVisualWorkflowElement(initial, { kind: "node", id: "risk-check" });
    const moved = moveVisualWorkflowNode(selected, "risk-check", { x: 812, y: 42 });

    expect(moved.changed).toBe(true);
    expect(moved.state.nodes.find((node) => node.id === "risk-check")?.position).toEqual({
      x: 812,
      y: 42,
    });

    const deleted = removeSelectedVisualWorkflowElement(moved.state);
    expect(deleted.changed).toBe(true);
    expect(deleted.state.nodes.some((node) => node.id === "risk-check")).toBe(false);
    expect(
      deleted.state.edges.some(
        (edge) => edge.source === "risk-check" || edge.target === "risk-check",
      ),
    ).toBe(false);
    expect(deleted.state.selection).toBeNull();
  });

  it("connects and removes safe edges while rejecting duplicate and unsafe connections", () => {
    const initial = createInitialVisualWorkflowEditorState();
    const withoutGateEdge = removeVisualWorkflowEdge(
      initial,
      "risk-check-to-approval-ticket",
    ).state;
    const connected = connectVisualWorkflowNodes(
      withoutGateEdge,
      "risk-check",
      "approval-ticket",
    );

    expect(connected.changed).toBe(true);
    expect(connected.state.edges).toContainEqual({
      id: "risk-check-to-approval-ticket",
      source: "risk-check",
      target: "approval-ticket",
      type: "workflow",
    });
    expect(connected.state.selection).toEqual({
      kind: "edge",
      id: "risk-check-to-approval-ticket",
    });

    expect(
      connectVisualWorkflowNodes(
        connected.state,
        "risk-check",
        "approval-ticket",
      ).reason,
    ).toBe("duplicate_edge");
    expect(
      connectVisualWorkflowNodes(connected.state, "missing", "approval-ticket").reason,
    ).toBe("unknown_endpoint");
    expect(
      connectVisualWorkflowNodes(connected.state, "risk-check", "risk-check").reason,
    ).toBe("self_connection");
    expect(
      connectVisualWorkflowNodes(
        connected.state,
        "risk-check",
        "approval-ticket",
        "broker_route",
      ).reason,
    ).toBe("unsupported_edge_type");

    const removed = removeSelectedVisualWorkflowElement(connected.state);
    expect(removed.changed).toBe(true);
    expect(
      removed.state.edges.some((edge) => edge.id === "risk-check-to-approval-ticket"),
    ).toBe(false);
    expect(removed.state.nodes).toEqual(connected.state.nodes);
  });

  it("resets graph content and selection to a fresh deterministic state", () => {
    const initial = createInitialVisualWorkflowEditorState();

    const reset = resetVisualWorkflowEditorState();

    expect(reset).toEqual(createInitialVisualWorkflowEditorState());
    expect(reset).not.toBe(initial);
  });
});
