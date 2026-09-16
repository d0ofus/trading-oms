import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Connection,
  type NodeProps,
} from "@xyflow/react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  Check,
  Copy,
  GitBranch,
  LayoutList,
  Plus,
  Redo2,
  Save,
  Search,
  Trash2,
  Undo2,
} from "lucide-react";
import {
  api,
  ApiError,
  preference,
  readPreference,
  titleCase,
  type Block,
  type Contract,
  type Draft,
  type Explanation,
  type Graph,
  type Issue,
  type Spec,
  type Template,
  type Version,
} from "./api";
import { Badge, Empty, Modal } from "./components";
import "@xyflow/react/dist/style.css";

function StrategyNode({ data, selected }: NodeProps) {
  const block = data.block as Block;
  const spec = data.spec as Spec;
  return (
    <div
      className={`ws-flow-node ${selected ? "selected" : ""} kind-${block.kind}`}
    >
      <span className="ws-eyebrow">{spec.group}</span>
      <strong>{block.label || spec.label}</strong>
      <small>
        {Object.entries(block.params)
          .filter(([key]) => key !== "source")
          .map(
            ([key, value]) =>
              `${key === "field" ? "" : `${titleCase(key)}: `}${titleCase(String(value))}`,
          )
          .join(" · ") || "Strategy output"}
      </small>
      {Object.keys(spec.inputs).map((port, index) => (
        <Handle
          key={port}
          id={port}
          type="target"
          role="img"
          position={Position.Left}
          style={{ top: `${45 + index * 28}%` }}
          aria-label={`${spec.label} input ${port}`}
        />
      ))}
      <Handle
        type="source"
        role="img"
        position={Position.Right}
        aria-label={`${spec.label} output`}
      />
    </div>
  );
}
const nodeTypes = { strategy: StrategyNode };
const copy = <T,>(value: T): T => structuredClone(value);
const signature = (draft: Draft) =>
  JSON.stringify([draft.name, draft.document]);

export function Studio({
  contracts,
  notify,
  createRun,
}: {
  contracts: Contract[];
  notify: (message: string, error?: boolean) => void;
  createRun: (version: Version) => void;
}) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [catalog, setCatalog] = useState<Spec[]>([]);
  const [active, setActive] = useState<Draft | null>(null);
  const [view, setView] = useState(() =>
    readPreference("studio.view", "guided"),
  );
  const [saveState, setSaveState] = useState("Saved");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [explanation, setExplanation] = useState<Explanation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [blockSearch, setBlockSearch] = useState("");
  const [librarySearch, setLibrarySearch] = useState("");
  const [publishOpen, setPublishOpen] = useState(false);
  const [versions, setVersions] = useState<Version[]>([]);
  const [history, setHistory] = useState<Graph[]>([]);
  const [future, setFuture] = useState<Graph[]>([]);
  const [busy, setBusy] = useState(false);
  const [libraryWidth, setLibraryWidth] = useState(() =>
    readPreference("studio.libraryWidth", 224),
  );
  const saved = useRef("");
  const saving = useRef(false);
  const activeRef = useRef(active);
  const dragStart = useRef<Graph | null>(null);
  activeRef.current = active;

  const selectDraft = useCallback((draft: Draft) => {
    saved.current = signature(draft);
    const recovered = readPreference<Draft | null>(
      `recovery.${draft.id}`,
      null,
    );
    const dirty = recovered && signature(recovered) !== signature(draft);
    setActive(dirty ? recovered : draft);
    setSaveState(
      dirty && recovered.revision !== draft.revision
        ? "Conflict"
        : dirty
          ? "Recovered draft"
          : "Saved",
    );
    setSelected(null);
    setHistory([]);
    setFuture([]);
    preference("studio.selected", draft.id);
    void api<Version[]>(`/strategies/${draft.id}/versions`)
      .then((items) => {
        if (activeRef.current?.id === draft.id) setVersions(items);
      })
      .catch(() => setVersions([]));
  }, []);

  useEffect(() => {
    let live = true;
    void Promise.all([
      api<Draft[]>("/strategies"),
      api<{ templates: Template[]; blocks: Spec[] }>("/strategies/catalog"),
    ])
      .then(([items, data]) => {
        if (!live) return;
        setDrafts(items);
        setTemplates(data.templates);
        setCatalog(data.blocks);
        const selectedId = readPreference("studio.selected", "");
        const item = items.find((draft) => draft.id === selectedId) ?? items[0];
        if (item) selectDraft(item);
      })
      .catch((error: Error) => notify(error.message, true));
    return () => {
      live = false;
    };
  }, [selectDraft, notify]);

  useEffect(() => {
    if (!active) return;
    preference(`recovery.${active.id}`, active);
    if (signature(active) === saved.current || saveState === "Conflict") return;
    const timer = setTimeout(() => {
      if (saving.current) return;
      saving.current = true;
      setSaveState("Saving…");
      const submitted = copy(active);
      void api<Draft>(`/strategies/${active.id}`, "PUT", {
        name: submitted.name,
        document: submitted.document,
        revision: submitted.revision,
      })
        .then((response) => {
          if (activeRef.current?.id !== response.id) return;
          saved.current = signature(submitted);
          setActive((current) =>
            current && current.id === response.id
              ? {
                  ...current,
                  revision: response.revision,
                  updated_at: response.updated_at,
                }
              : current,
          );
          setDrafts((items) =>
            items.map((draft) => (draft.id === response.id ? response : draft)),
          );
          setSaveState("Saved");
        })
        .catch((error: ApiError) => {
          setSaveState(
            error.status === 409 ? "Conflict" : "Offline · kept on this device",
          );
        })
        .finally(() => {
          saving.current = false;
        });
    }, 850);
    return () => clearTimeout(timer);
  }, [active, saveState]);

  useEffect(() => {
    if (!active) return;
    let current = true;
    const timer = setTimeout(() => {
      void api<{ explanation: Explanation[] }>("/strategies/validate", "POST", {
        document: active.document,
      })
        .then((response) => {
          if (current) {
            setIssues([]);
            setExplanation(response.explanation);
          }
        })
        .catch((error: ApiError) => {
          if (current) {
            setIssues(
              error.issues.length
                ? error.issues
                : [{ code: "validation_unavailable", message: error.message }],
            );
            setExplanation([]);
          }
        });
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [active]);

  const update = (document: Graph) => {
    if (!active) return;
    setHistory((items) => [...items.slice(-49), copy(active.document)]);
    setFuture([]);
    setActive({ ...active, document });
    if (saveState !== "Conflict") setSaveState("Unsaved changes");
  };
  const modify = (action: (document: Graph) => void) => {
    if (active) {
      const document = copy(active.document);
      action(document);
      update(document);
    }
  };
  const undo = () => {
    if (active && history.length) {
      setFuture((items) => [active.document, ...items]);
      setActive({ ...active, document: history[history.length - 1] });
      setHistory(history.slice(0, -1));
      setSaveState("Unsaved changes");
    }
  };
  const redo = () => {
    if (active && future.length) {
      setHistory((items) => [...items, active.document]);
      setActive({ ...active, document: future[0] });
      setFuture(future.slice(1));
      setSaveState("Unsaved changes");
    }
  };

  async function newDraft(name: string, document: Graph) {
    try {
      const draft = await api<Draft>("/strategies", "POST", {
        name,
        document,
        revision: 0,
      });
      setDrafts((items) => [draft, ...items]);
      preference(`recovery.${draft.id}`, draft);
      selectDraft(draft);
      notify("Draft created. Changes save automatically.");
    } catch (error) {
      notify((error as Error).message, true);
    }
  }
  function addBlock(spec: Spec) {
    const id = "block_" + crypto.randomUUID().slice(0, 8);
    modify((document) =>
      document.nodes.push({
        id,
        kind: spec.kind,
        label: spec.label,
        params: copy(spec.defaults),
        position: { x: 260, y: document.nodes.length * 70 },
      }),
    );
    setSelected(id);
    setBlockSearch("");
  }
  function connect(connection: Connection) {
    if (
      !active ||
      !connection.source ||
      !connection.target ||
      !connection.targetHandle
    )
      return;
    const source = active.document.nodes.find(
      (node) => node.id === connection.source,
    );
    const target = active.document.nodes.find(
      (node) => node.id === connection.target,
    );
    const sourceSpec = catalog.find((spec) => spec.kind === source?.kind);
    const targetSpec = catalog.find((spec) => spec.kind === target?.kind);
    if (
      source?.id === target?.id ||
      sourceSpec?.output !== targetSpec?.inputs[connection.targetHandle]
    ) {
      notify(
        "Connect a compatible value to this input. A block cannot feed itself.",
        true,
      );
      return;
    }
    const edges = [
      ...active.document.edges.filter(
        (edge) =>
          !(
            edge.target === connection.target &&
            edge.input === connection.targetHandle
          ),
      ),
      {
        source: connection.source,
        target: connection.target,
        input: connection.targetHandle,
      },
    ];
    const reaches = (at: string, seen = new Set<string>()): boolean => {
      if (at === connection.source) return true;
      if (seen.has(at)) return false;
      seen.add(at);
      return edges
        .filter((edge) => edge.source === at)
        .some((edge) => reaches(edge.target, seen));
    };
    if (reaches(connection.target)) {
      notify(
        "This connection creates a cycle. Choose an earlier calculation.",
        true,
      );
      return;
    }
    update({ ...active.document, edges });
  }
  function blockEditor(block: Block) {
    const spec = catalog.find((item) => item.kind === block.kind);
    if (!spec) return null;
    const change = (key: string, value: string | number) =>
      modify((document) => {
        const node = document.nodes.find((n) => n.id === block.id);
        if (node) node.params[key] = value;
      });
    return (
      <div className="ws-block-fields">
        <label>
          Block name
          <input
            value={block.label || spec.label}
            maxLength={100}
            onChange={(event) =>
              modify((document) => {
                const node = document.nodes.find((n) => n.id === block.id);
                if (node) node.label = event.target.value;
              })
            }
          />
        </label>
        {Object.entries(block.params).map(([key, value]) => {
          const field = String(block.params.field ?? "");
          if (
            block.kind === "field" &&
            key === "period" &&
            ![
              "sma",
              "ema",
              "rolling_high",
              "rolling_low",
              "opening_high",
              "opening_low",
            ].includes(field)
          )
            return null;
          if (
            block.kind === "field" &&
            key === "source" &&
            [
              "last",
              "session_volume",
              "relative_volume",
              "opening_high",
              "opening_low",
              "session_low",
            ].includes(field)
          )
            return null;
          const options =
            key === "field"
              ? spec.fields
              : key === "source"
                ? ["current", "closed"]
                : ["op", "direction"].includes(key)
                  ? spec.choices
                  : undefined;
          return (
            <label key={key}>
              {key === "source"
                ? "Candle input"
                : key === "period"
                  ? field.startsWith("opening_")
                    ? "Opening range · minutes"
                    : "Lookback · bars"
                  : titleCase(key)}
              {options ? (
                <select
                  value={value}
                  onChange={(event) => change(key, event.target.value)}
                >
                  {options.map((option) => (
                    <option key={option} value={option}>
                      {option === "closed"
                        ? "Completed candle"
                        : option === "current"
                          ? "Forming candle"
                          : titleCase(option)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  step={key === "value" ? "any" : "1"}
                  value={value}
                  onChange={(event) =>
                    change(
                      key,
                      event.target.value === ""
                        ? ""
                        : key === "value"
                          ? event.target.value
                          : Number(event.target.value),
                    )
                  }
                />
              )}
            </label>
          );
        })}
        {Object.entries(spec.inputs).map(([port, type]) => (
          <label key={port}>
            Input {port.toUpperCase()} ·{" "}
            {type === "boolean" ? "condition" : "value"}
            <select
              value={
                active?.document.edges.find(
                  (edge) => edge.target === block.id && edge.input === port,
                )?.source ?? ""
              }
              onChange={(event) => {
                if (event.target.value)
                  connect({
                    source: event.target.value,
                    target: block.id,
                    sourceHandle: null,
                    targetHandle: port,
                  });
                else
                  modify((document) => {
                    document.edges = document.edges.filter(
                      (edge) => edge.target !== block.id || edge.input !== port,
                    );
                  });
              }}
            >
              <option value="">Choose a calculation…</option>
              {active?.document.nodes
                .filter(
                  (node) =>
                    node.id !== block.id &&
                    catalog.find((item) => item.kind === node.kind)?.output ===
                      type,
                )
                .map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.label || titleCase(node.kind)}
                    {node.params.field
                      ? ` · ${titleCase(String(node.params.field))}`
                      : ""}
                    {node.params.period ? ` (${node.params.period})` : ""}
                  </option>
                ))}
            </select>
          </label>
        ))}
        <div className="ws-inline-actions">
          <button
            onClick={() => {
              const id = "block_" + crypto.randomUUID().slice(0, 8);
              modify((document) => {
                document.nodes.push({
                  ...copy(block),
                  id,
                  label: `${block.label || spec.label} copy`,
                  position: {
                    x: (block.position?.x || 0) + 40,
                    y: (block.position?.y || 0) + 100,
                  },
                });
                document.edges.push(
                  ...document.edges
                    .filter((edge) => edge.target === block.id)
                    .map((edge) => ({ ...edge, target: id })),
                );
              });
              setSelected(id);
            }}
          >
            <Copy size={14} />
            Duplicate block
          </button>
          <button
            className="ws-danger-text"
            onClick={() => {
              modify((document) => {
                document.nodes = document.nodes.filter(
                  (node) => node.id !== block.id,
                );
                document.edges = document.edges.filter(
                  (edge) =>
                    edge.target !== block.id && edge.source !== block.id,
                );
              });
              setSelected(null);
            }}
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      </div>
    );
  }
  const settings = active?.document.settings;
  function focusRule(identity: string) {
    setSelected(identity);
    setView("guided");
    preference("studio.view", "guided");
    window.requestAnimationFrame(() => {
      const target = window.document.getElementById(`rule-${identity}`);
      target?.scrollIntoView({ block: "center" });
      target?.querySelector<HTMLElement>("input, select, summary")?.focus();
    });
  }
  function setting(
    key: string,
    label: string,
    options?: [string | number, string][],
    unit?: string,
  ) {
    if (!settings) return null;
    return (
      <label key={key}>
        {label}
        {options ? (
          <select
            value={settings[key]}
            onChange={(event) =>
              modify((document) => {
                document.settings[key] =
                  typeof settings[key] === "number"
                    ? Number(event.target.value)
                    : event.target.value;
              })
            }
          >
            {options.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        ) : (
          <div className="ws-unit-input">
            <input
              value={settings[key]}
              type={key === "symbol" ? "text" : "number"}
              list={key === "symbol" ? "ws-contract-symbols" : undefined}
              onChange={(event) =>
                modify((document) => {
                  document.settings[key] =
                    key === "symbol"
                      ? event.target.value.toUpperCase()
                      : [
                            "shares",
                            "entry_timeout",
                            "max_entries",
                            "exit_before_close",
                          ].includes(key) && event.target.value !== ""
                        ? Number(event.target.value)
                        : event.target.value;
                })
              }
            />
            {unit && <span>{unit}</span>}
          </div>
        )}
      </label>
    );
  }
  const groups = new Map<string, string>();
  if (active) {
    const ancestors = (kinds: string[]) => {
      const ids = new Set(
        active.document.nodes
          .filter((n) => kinds.includes(n.kind))
          .map((n) => n.id),
      );
      let changed = true;
      while (changed) {
        changed = false;
        for (const edge of active.document.edges)
          if (ids.has(edge.target) && !ids.has(edge.source)) {
            ids.add(edge.source);
            changed = true;
          }
      }
      return ids;
    };
    const entry = ancestors(["entry"]),
      protection = ancestors(["stop", "target"]),
      exit = ancestors(["exit"]);
    for (const node of active.document.nodes)
      groups.set(
        node.id,
        entry.has(node.id)
          ? "entry"
          : protection.has(node.id)
            ? "protection"
            : exit.has(node.id)
              ? "exit"
              : "entry",
      );
  }
  function rules(group: string) {
    return (
      <div className="ws-rule-list">
        {(active?.document.nodes ?? [])
          .filter((block) => groups.get(block.id) === group)
          .map((block) => (
            <details
              id={`rule-${block.id}`}
              key={block.id}
              className={`ws-rule ${selected === block.id ? "selected" : ""}`}
              open={
                selected === block.id ||
                ["entry", "stop", "exit", "target"].includes(block.kind)
              }
              onToggle={(event) => {
                if (
                  event.currentTarget.open &&
                  !["entry", "stop", "exit", "target"].includes(block.kind)
                )
                  setSelected(block.id);
              }}
            >
              <summary>
                <span className={`ws-rule-type kind-${block.kind}`}>
                  {catalog.find((item) => item.kind === block.kind)?.group}
                </span>
                <strong>{block.label || titleCase(block.kind)}</strong>
                <small>
                  {block.params.field
                    ? titleCase(String(block.params.field))
                    : ""}
                  {block.params.value ? ` · ${block.params.value}` : ""}
                </small>
              </summary>
              {blockEditor(block)}
            </details>
          ))}
      </div>
    );
  }
  const selectedBlock = active?.document.nodes.find(
    (node) => node.id === selected,
  );
  const changedRules = active
    ? active.document.nodes.filter((node) => {
        const old = versions[0]?.document.nodes.find(
          (item) => item.id === node.id,
        );
        return (
          !old ||
          JSON.stringify([old.kind, old.params]) !==
            JSON.stringify([node.kind, node.params])
        );
      })
    : [];
  const changedConnections =
    active &&
    JSON.stringify(active.document.edges) !==
      JSON.stringify(versions[0]?.document.edges);

  return (
    <div
      className="ws-studio"
      style={{ gridTemplateColumns: `${libraryWidth}px minmax(0, 1fr)` }}
    >
      <aside className="ws-library">
        <div className="ws-panel-heading">
          <div>
            <h2>Strategy library</h2>
            <p>Drafts and published versions</p>
          </div>
        </div>
        <label className="ws-search">
          <Search size={15} />
          <input
            aria-label="Search strategies"
            placeholder="Find a strategy…"
            value={librarySearch}
            onChange={(event) => setLibrarySearch(event.target.value)}
          />
        </label>
        <div className="ws-library-items">
          {drafts
            .filter((draft) =>
              draft.name.toLowerCase().includes(librarySearch.toLowerCase()),
            )
            .map((draft) => (
              <button
                key={draft.id}
                className={`ws-library-item ${active?.id === draft.id ? "active" : ""}`}
                onClick={() => selectDraft(draft)}
              >
                <GitBranch size={17} />
                <span>
                  <strong>{draft.name}</strong>
                  <small>
                    {draft.document.settings.symbol} ·{" "}
                    {draft.published_version
                      ? `Published v${draft.published_version}`
                      : "Unpublished draft"}
                  </small>
                </span>
              </button>
            ))}
        </div>
        <div className="ws-library-templates">
          <span className="ws-eyebrow">START FROM A TEMPLATE</span>
          {templates.map((template) => (
            <button
              key={template.id}
              onClick={() =>
                void newDraft(template.name, copy(template.document))
              }
            >
              <Plus size={15} />
              <span>
                {template.name}
                <small>{template.description}</small>
              </span>
            </button>
          ))}
        </div>
        <details className="ws-library-options">
          <summary>Panel preferences</summary>
          <label>
            Library width
            <input
              type="range"
              min="180"
              max="320"
              value={libraryWidth}
              onChange={(event) => {
                setLibraryWidth(Number(event.target.value));
                preference("studio.libraryWidth", Number(event.target.value));
              }}
            />
          </label>
        </details>
      </aside>
      <section className="ws-editor">
        {!active ? (
          <Empty
            title="Build your first strategy"
            action={
              <button
                className="ws-primary"
                onClick={() =>
                  templates[0] &&
                  void newDraft(templates[0].name, copy(templates[0].document))
                }
              >
                <Plus size={16} />
                Use opening range template
              </button>
            }
          >
            Start with a template, define your trading rules, then test and
            publish an immutable version.
          </Empty>
        ) : (
          <>
            <div className="ws-editor-heading">
              <div className="ws-strategy-name">
                <input
                  aria-label="Strategy name"
                  value={active.name}
                  maxLength={100}
                  onChange={(event) => {
                    setActive({ ...active, name: event.target.value });
                    setSaveState("Unsaved changes");
                  }}
                />
                <span className="ws-save-state" role="status">
                  {saveState === "Saved" ? (
                    <Check size={13} />
                  ) : (
                    <Save size={13} />
                  )}
                  {saveState}
                  {active.published_version > 0 &&
                    ` · Running versions stay pinned`}
                </span>
              </div>
              <div className="ws-inline-actions">
                <button
                  aria-label="Undo edit"
                  disabled={!history.length}
                  onClick={undo}
                >
                  <Undo2 size={16} />
                </button>
                <button
                  aria-label="Redo edit"
                  disabled={!future.length}
                  onClick={redo}
                >
                  <Redo2 size={16} />
                </button>
                <button
                  title="Duplicate strategy"
                  onClick={() =>
                    void newDraft(`${active.name} copy`, copy(active.document))
                  }
                >
                  <Copy size={15} />
                  <span>Duplicate</span>
                </button>
                <button
                  className="ws-primary"
                  disabled={saveState !== "Saved" || issues.length > 0}
                  onClick={() => setPublishOpen(true)}
                >
                  Review & publish
                </button>
              </div>
            </div>
            {saveState === "Conflict" && (
              <div className="ws-banner danger" role="alert">
                <strong>This draft changed in another session.</strong>
                <span>
                  Your edits are retained on this device. Save a copy or load
                  the current server draft.
                </span>
                <button
                  onClick={() =>
                    void newDraft(`${active.name} recovered`, active.document)
                  }
                >
                  Save my copy
                </button>
                <button
                  onClick={() => {
                    void api<Draft[]>("/strategies").then((items) => {
                      const latest = items.find(
                        (item) => item.id === active.id,
                      );
                      if (latest) {
                        preference(`conflict-backup.${active.id}`, active);
                        preference(`recovery.${active.id}`, latest);
                        selectDraft(latest);
                      }
                    });
                  }}
                >
                  Load latest draft
                </button>
              </div>
            )}
            <Tabs.Root
              value={view}
              onValueChange={(value) => {
                setView(value);
                preference("studio.view", value);
              }}
              className="ws-editor-tabs"
            >
              <div className="ws-editor-toolbar">
                <Tabs.List aria-label="Strategy editor view">
                  <Tabs.Trigger value="guided">
                    <LayoutList size={15} />
                    Guided configuration
                  </Tabs.Trigger>
                  <Tabs.Trigger value="canvas">
                    <GitBranch size={15} />
                    Canvas
                  </Tabs.Trigger>
                </Tabs.List>
                <Badge tone={issues.length ? "warning" : "success"}>
                  {issues.length
                    ? `${issues.length} issue to resolve`
                    : "Valid strategy"}
                </Badge>
              </div>
              {issues.length > 0 && (
                <div className="ws-validation" role="status">
                  {issues.map((issue, index) => (
                    <button
                      key={index}
                      onClick={() => {
                        focusRule(issue.node ?? "settings");
                      }}
                    >
                      {issue.message}
                      {issue.node && " · Go to rule ↗"}
                    </button>
                  ))}
                </div>
              )}
              <div className="ws-studio-body">
                <div className="ws-editor-main">
                  <Tabs.Content value="guided" className="ws-guided">
                    <section className="ws-config-section" id="rule-settings">
                      <div className="ws-section-number">01</div>
                      <div>
                        <h3>Market & session</h3>
                        <p>
                          Regular US exchange hours. Session boundaries adjust
                          for holidays and early closes.
                        </p>
                        <div className="ws-form-grid">
                          {setting("symbol", "Stock or ETF symbol")}
                          {setting("timeframe", "Candle interval", [
                            [5, "5 seconds"],
                            [60, "1 minute"],
                            [300, "5 minutes"],
                          ])}
                          {setting("evaluation", "Evaluate conditions", [
                            ["intrabar", "On each trade · intrabar"],
                            ["bar_close", "At completed candle"],
                          ])}
                        </div>
                        <datalist id="ws-contract-symbols">
                          {contracts.map((contract) => (
                            <option
                              key={contract.conid}
                              value={contract.symbol}
                            >
                              {contract.name}
                            </option>
                          ))}
                        </datalist>
                      </div>
                    </section>
                    <section className="ws-config-section">
                      <div className="ws-section-number">02</div>
                      <div>
                        <h3>Entry conditions & shared calculations</h3>
                        <p>
                          Choose typed inputs below or connect the same blocks
                          on the canvas. Shared calculations have one
                          definition.
                        </p>
                        {rules("entry")}
                      </div>
                    </section>
                    <section className="ws-config-section">
                      <div className="ws-section-number">03</div>
                      <div>
                        <h3>Position sizing</h3>
                        <p>
                          Gaps can exceed planned stop risk. The session risk
                          profile can impose tighter limits.
                        </p>
                        <div className="ws-form-grid">
                          {setting("sizing", "Sizing method", [
                            ["risk", "Planned stop risk"],
                            ["fixed", "Fixed shares"],
                          ])}
                          {setting(
                            "risk",
                            "Planned stop risk",
                            undefined,
                            "USD",
                          )}
                          {setting(
                            "shares",
                            "Fixed-share ceiling",
                            undefined,
                            "shares",
                          )}
                          {setting(
                            "notional",
                            "Notional ceiling",
                            undefined,
                            "USD",
                          )}
                        </div>
                      </div>
                    </section>
                    <section className="ws-config-section">
                      <div className="ws-section-number">04</div>
                      <div>
                        <h3>Protective stop & profit target</h3>
                        <p>
                          A stop is mandatory. Add a profit-target block when
                          the strategy needs one.
                        </p>
                        {rules("protection")}
                      </div>
                    </section>
                    <section className="ws-config-section">
                      <div className="ws-section-number">05</div>
                      <div>
                        <h3>Conditional & time exits</h3>
                        <p>
                          Existing positions retain their published exit rules
                          after disarming.
                        </p>
                        {rules("exit")}
                        {setting(
                          "exit_before_close",
                          "Initiate session exit",
                          undefined,
                          "min before close",
                        )}
                      </div>
                    </section>
                    <section className="ws-config-section">
                      <div className="ws-section-number">06</div>
                      <div>
                        <h3>Execution limits</h3>
                        <p>
                          Entries stop 15 minutes before exchange close. Every
                          entry passes account-wide risk checks.
                        </p>
                        <div className="ws-form-grid">
                          {setting(
                            "max_entries",
                            "Entries per session",
                            undefined,
                            "entries",
                          )}
                          {setting(
                            "entry_timeout",
                            "Working entry lifetime",
                            undefined,
                            "seconds",
                          )}
                        </div>
                      </div>
                    </section>
                  </Tabs.Content>
                  <Tabs.Content value="canvas" className="ws-canvas">
                    <div className="ws-canvas-tools">
                      <span>
                        Drag connections or select a block to choose inputs.
                      </span>
                      <button
                        onClick={() =>
                          modify((document) => {
                            document.nodes.forEach((node, index) => {
                              node.position = {
                                x: (index % 4) * 270,
                                y: Math.floor(index / 4) * 150,
                              };
                            });
                          })
                        }
                      >
                        Auto-layout
                      </button>
                    </div>
                    <ReactFlow
                      nodeTypes={nodeTypes}
                      nodes={active.document.nodes.map((block, index) => ({
                        id: block.id,
                        type: "strategy",
                        position: block.position ?? {
                          x: (index % 4) * 270,
                          y: Math.floor(index / 4) * 150,
                        },
                        data: {
                          block,
                          spec: catalog.find(
                            (item) => item.kind === block.kind,
                          ),
                        },
                        selected: selected === block.id,
                      }))}
                      edges={active.document.edges.map((edge) => ({
                        id: `${edge.source}-${edge.target}-${edge.input}`,
                        source: edge.source,
                        target: edge.target,
                        targetHandle: edge.input,
                        type: "smoothstep",
                      }))}
                      onNodeClick={(_, node) => setSelected(node.id)}
                      onNodeDragStart={() => {
                        dragStart.current = active
                          ? copy(active.document)
                          : null;
                      }}
                      onNodesChange={(changes) => {
                        for (const change of changes) {
                          if (change.type === "select" && change.selected)
                            setSelected(change.id);
                          if (change.type === "position" && change.position) {
                            setActive((previous) =>
                              previous
                                ? {
                                    ...previous,
                                    document: {
                                      ...previous.document,
                                      nodes: previous.document.nodes.map((n) =>
                                        n.id === change.id
                                          ? { ...n, position: change.position }
                                          : n,
                                      ),
                                    },
                                  }
                                : previous,
                            );
                          }
                        }
                      }}
                      onNodeDragStop={(_, node) => {
                        if (dragStart.current) {
                          setHistory((items) => [
                            ...items.slice(-49),
                            dragStart.current!,
                          ]);
                          setFuture([]);
                          dragStart.current = null;
                        }
                        setSaveState("Unsaved changes");
                        setSelected(node.id);
                      }}
                      onConnect={connect}
                      onEdgesDelete={(edges) =>
                        modify((document) => {
                          const removed = new Set(edges.map((edge) => edge.id));
                          document.edges = document.edges.filter(
                            (edge) =>
                              !removed.has(
                                `${edge.source}-${edge.target}-${edge.input}`,
                              ),
                          );
                        })
                      }
                      fitView
                      minZoom={0.2}
                      maxZoom={1.5}
                      colorMode={
                        window.document.documentElement.dataset.theme ===
                        "light"
                          ? "light"
                          : "dark"
                      }
                      nodesFocusable
                      edgesFocusable
                      deleteKeyCode={null}
                    >
                      <Background gap={20} />
                      <Controls showInteractive={false} />
                      <MiniMap pannable zoomable />
                    </ReactFlow>
                  </Tabs.Content>
                </div>
                <aside className="ws-inspector">
                  {selectedBlock && view === "canvas" ? (
                    <>
                      <span className="ws-eyebrow">SELECTED BLOCK</span>
                      <h3>
                        {selectedBlock.label || titleCase(selectedBlock.kind)}
                      </h3>
                      {blockEditor(selectedBlock)}
                    </>
                  ) : (
                    <>
                      <span className="ws-eyebrow">STRATEGY EXPLANATION</span>
                      <h3>What this strategy does</h3>
                      {explanation.length ? (
                        explanation.map((item) => (
                          <button
                            key={`${item.node}-${item.kind}`}
                            className="ws-explanation"
                            onClick={() => {
                              focusRule(item.node);
                            }}
                          >
                            <strong>{titleCase(item.kind)}</strong>
                            <span>{item.text}</span>
                          </button>
                        ))
                      ) : (
                        <p className="ws-muted">
                          Resolve validation issues to generate an exact
                          executable summary.
                        </p>
                      )}
                    </>
                  )}
                  <div className="ws-block-catalog">
                    <h3>Add a block</h3>
                    <label className="ws-search">
                      <Search size={15} />
                      <input
                        aria-label="Search blocks"
                        value={blockSearch}
                        onChange={(event) => setBlockSearch(event.target.value)}
                        placeholder="Search calculations…"
                      />
                    </label>
                    {catalog
                      .filter((spec) =>
                        `${spec.label} ${spec.group}`
                          .toLowerCase()
                          .includes(blockSearch.toLowerCase()),
                      )
                      .map((spec) => (
                        <button key={spec.kind} onClick={() => addBlock(spec)}>
                          <Plus size={14} />
                          <span>
                            {spec.label}
                            <small>{spec.group}</small>
                          </span>
                        </button>
                      ))}
                  </div>
                  <details className="ws-diagnostics">
                    <summary>Advanced diagnostics</summary>
                    <p>
                      Draft revision {active.revision} · Schema{" "}
                      {active.document.schema_version}
                    </p>
                    {versions[0] && <code>{versions[0].hash}</code>}
                  </details>
                </aside>
              </div>
            </Tabs.Root>
            <Modal
              open={publishOpen}
              onOpenChange={setPublishOpen}
              title="Review executable version"
              description="Publication creates an immutable version. Active runs retain their current rules and exit contract."
              wide
            >
              <div className="ws-publish-review">
                <div>
                  <h3>{active.name}</h3>
                  <p>
                    {active.document.settings.symbol} ·{" "}
                    {titleCase(String(active.document.settings.evaluation))} ·{" "}
                    {active.document.settings.timeframe}-second candles
                  </p>
                  {explanation.map((item) => (
                    <div
                      key={`${item.node}-${item.kind}`}
                      className="ws-summary-line"
                    >
                      <strong>{titleCase(item.kind)}</strong>
                      <p>{item.text}</p>
                    </div>
                  ))}
                </div>
                <div>
                  <h3>
                    Changes from{" "}
                    {versions[0]
                      ? `version ${versions[0].version}`
                      : "template draft"}
                  </h3>
                  <ul>
                    {changedRules.map((node) => (
                      <li key={node.id}>
                        {node.label || titleCase(node.kind)}: parameters added
                        or changed
                      </li>
                    ))}
                    {versions[0]?.document.nodes
                      .filter(
                        (node) =>
                          !active.document.nodes.some(
                            (item) => item.id === node.id,
                          ),
                      )
                      .map((node) => (
                        <li key={node.id}>{node.label}: removed</li>
                      ))}
                    {changedConnections && (
                      <li>
                        Rule connections changed; review the exact grouping
                        opposite.
                      </li>
                    )}
                    {JSON.stringify(active.document.settings) !==
                      JSON.stringify(versions[0]?.document.settings) && (
                      <li>
                        Market, evaluation, sizing or session limits changed.
                      </li>
                    )}
                  </ul>
                  <p className="ws-muted">
                    Canvas placement and block names do not change the execution
                    hash.
                  </p>
                </div>
              </div>
              <div className="ws-modal-actions">
                <button onClick={() => setPublishOpen(false)}>
                  Keep editing
                </button>
                {versions[0] && (
                  <button
                    onClick={() => {
                      createRun(versions[0]);
                      setPublishOpen(false);
                    }}
                  >
                    Prepare published v{versions[0].version}
                  </button>
                )}
                <button
                  className="ws-primary"
                  disabled={busy || issues.length > 0 || saveState !== "Saved"}
                  onClick={() => {
                    setBusy(true);
                    void api<Version>(
                      `/strategies/${active.id}/publish`,
                      "POST",
                      { revision: active.revision },
                    )
                      .then(async (version) => {
                        setVersions((items) => [version, ...items]);
                        const items = await api<Draft[]>("/strategies");
                        setDrafts(items);
                        const latest = items.find(
                          (item) => item.id === active.id,
                        );
                        if (latest) {
                          preference(`recovery.${latest.id}`, latest);
                          selectDraft(latest);
                        }
                        setPublishOpen(false);
                        notify(
                          `Version ${version.version} published. Test it before arming a paper session.`,
                        );
                      })
                      .catch((error: Error) => notify(error.message, true))
                      .finally(() => setBusy(false));
                  }}
                >
                  {busy ? "Publishing…" : "Publish version"}
                </button>
              </div>
            </Modal>
          </>
        )}
      </section>
    </div>
  );
}
