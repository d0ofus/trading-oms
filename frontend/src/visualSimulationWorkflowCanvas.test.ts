import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  VisualSimulationWorkflowCanvas,
  visualSimulationWorkflowLayoutPolicy,
  visualSimulationWorkflowNodePalette,
} from "./visualSimulationWorkflowCanvas";
import {
  createInitialVisualWorkflowEditorState,
  removeVisualWorkflowNode,
} from "./visualWorkflowEditor";

describe("visualSimulationWorkflowCanvas", () => {
  it("exposes a compact palette for every typed simulation node", () => {
    expect(visualSimulationWorkflowNodePalette.map((node) => node.title)).toEqual([
      "Replay source",
      "Bar builder",
      "Strategy trigger",
      "Risk check",
      "Approval ticket",
      "Fake broker",
      "Position update",
      "Alert",
      "Audit sink",
    ]);
    expect(visualSimulationWorkflowNodePalette.every((node) => node.supportsExecution === false)).toBe(
      true,
    );
  });

  it("enables local graph editing while keeping persistence and execution disabled", () => {
    expect(visualSimulationWorkflowLayoutPolicy).toEqual({
      mode: "local_graph_editor",
      nodesDraggable: true,
      nodesConnectable: true,
      elementsSelectable: true,
      nodesDeletable: true,
      edgesDeletable: true,
      persistenceEnabled: false,
      executionEnabled: false,
      canvasMinHeightPx: 440,
      responsiveLayout: true,
    });
  });

  it("renders palette, graph tools, continuous validation, and stable canvas dimensions", () => {
    const html = renderCanvas(createInitialVisualWorkflowEditorState());
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(html).toContain('aria-label="Safe simulation node palette"');
    expect(html).toContain('aria-label="Add Replay source"');
    expect(html).toContain('aria-label="Add Audit sink"');
    expect(html).toContain('aria-label="Remove selected graph element"');
    expect(html).toContain('aria-label="Reset local workflow graph"');
    expect(html).toContain('aria-label="Interactive simulation workflow editor"');
    expect(html).toContain("--workflow-canvas-min-height:440px");
    expect(text).toContain("Node palette");
    expect(text).toContain("Graph validation passed");
    expect(text).toContain("Required simulation safety path connected");
    expect(text).toContain("Local graph only");
    expect(text).not.toContain("Run inspection statuses");
    expect(text).not.toContain("workflow-run-001");
  });

  it("renders current invalid graph errors and enables restoration from the typed palette", () => {
    const state = removeVisualWorkflowNode(
      createInitialVisualWorkflowEditorState(),
      "risk-check",
    ).state;
    const html = renderCanvas(state);
    const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

    expect(text).toContain("Graph validation blocked");
    expect(text).toContain("Missing required risk check node");
    expect(text).toContain("Required simulation safety path is incomplete");
    expect(html).toMatch(/aria-label="Add Risk check"(?![^>]*disabled)/);
  });

  it("keeps the editor free of persistence, execution, broker, credential, live, and code controls", () => {
    const html = renderCanvas(createInitialVisualWorkflowEditorState()).toLowerCase();

    for (const forbidden of [
      "save workflow",
      "run workflow",
      "start simulation",
      "connect broker",
      "account id",
      "credential field",
      "broker host",
      "broker port",
      "submit order",
      "transmit order",
      "live mode",
      "javascript",
      "eval(",
      "import script",
    ]) {
      expect(html).not.toContain(forbidden);
    }
  });
});

function renderCanvas(editorState: ReturnType<typeof createInitialVisualWorkflowEditorState>) {
  return renderToStaticMarkup(
    createElement(VisualSimulationWorkflowCanvas, {
      editorState,
      onEditorStateChange: () => undefined,
    }),
  );
}
