import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  api,
  money,
  mutationId,
  preference,
  readPreference,
  type Json,
} from "./api";
import { Badge, Panel } from "./components";

export type RiskProfile = {
  id: string;
  version: number;
  name: string;
  risk_policy?: string;
  stock_units?: number | null;
  fx_units?: number | null;
  shares?: number;
  quantity?: string;
  runs: number;
  planned_stop_risk: string | null;
  notional: string | null;
  daily_loss?: string; // Read-only historical profiles; never enforced.
  entry_timeout: number;
};
export const chosenProfile = () =>
  readPreference("riskProfile", { id: "smoke", version: 1 });

export function RiskSettings({
  notify,
  simulation = false,
}: {
  simulation?: boolean;
  notify: (message: string, error?: boolean) => void;
}) {
  const [profiles, setProfiles] = useState<RiskProfile[]>([]);
  const [selected, setSelected] = useState(chosenProfile);
  const [qualification, setQualification] = useState<Record<string, Json>>({});
  const [busy, setBusy] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [editing, setEditing] = useState(false);
  const form = useForm<RiskProfile>({
    defaultValues: {
      name: "My paper limits",
      ...(simulation ? { quantity: "10" } : { shares: 1 }),
      runs: 1,
      planned_stop_risk: "10",
      notional: "1000",
      entry_timeout: 30,
    },
  });
  useEffect(() => {
    void Promise.all([
      api<RiskProfile[]>("/risk-profiles"),
      api<Record<string, Json>>("/operations/qualification"),
    ])
      .then(([items, gate]) => {
        setProfiles(items);
        const previous = chosenProfile();
        const current =
          items.find(
            (p) =>
              p.id === previous.id &&
              p.version === previous.version &&
              p.daily_loss === undefined,
          ) ??
          items
            .filter((p) => p.id === previous.id && p.daily_loss === undefined)
            .sort((a, b) => b.version - a.version)[0] ??
          items.find((p) => p.id === "smoke" && p.daily_loss === undefined);
        if (current) {
          const value = { id: current.id, version: current.version };
          setSelected(value);
          preference("riskProfile", value);
        }
        setQualification(gate);
      })
      .catch((error: Error) => notify(error.message, true));
  }, [notify]);
  const profile = profiles.find(
    (p) => p.id === selected.id && p.version === selected.version,
  );
  async function accept(stage: string) {
    setBusy(true);
    try {
      await api("/operations/qualification", "POST", {
        stage,
        confirmed: reviewed,
      });
      setQualification(await api("/operations/qualification"));
      setReviewed(false);
      notify("Internal paper-stage acceptance recorded.");
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title={simulation ? "3. Set simulation limits" : "3. Set paper limits"}
      caption="Named, versioned limits are pinned when you arm a session."
    >
      <label>
        Default risk profile
        <select
          value={`${selected.id}:${selected.version}`}
          onChange={(event) => {
            const [id, version] = event.target.value.split(":");
            const value = { id, version: Number(version) };
            setSelected(value);
            preference("riskProfile", value);
          }}
        >
          {profiles
            .filter((item) => item.daily_loss === undefined)
            .map((item) => (
              <option
                key={`${item.id}:${item.version}`}
                value={`${item.id}:${item.version}`}
              >
                {item.name} · v{item.version}
              </option>
            ))}
        </select>
      </label>
      {profile && (
        <>
          <div className="ws-limit-grid">
            <div>
              <span>Concurrent runs</span>
              <strong>{profile.runs}</strong>
            </div>
            <div>
              <span>
                {profile.stock_units !== undefined
                  ? "Legal lot ceiling"
                  : simulation
                    ? "Quantity ceiling"
                    : "Share ceiling"}
              </span>
              <strong>
                {profile.stock_units !== undefined
                  ? (profile.stock_units ??
                    (profile.risk_policy === "paper_stock_v2"
                      ? "Selected quantity"
                      : "Risk sized"))
                  : (profile.quantity ?? profile.shares)}{" "}
                per run
              </strong>
            </div>
            <div>
              <span>Planned stop risk</span>
              <strong>
                {profile.planned_stop_risk == null
                  ? "No ceiling"
                  : money(profile.planned_stop_risk)}{" "}
                / run
              </strong>
            </div>
            <div>
              <span>Notional ceiling</span>
              <strong>
                {profile.notional == null
                  ? "No ceiling"
                  : money(profile.notional)}{" "}
                / run
              </strong>
            </div>
            <div>
              <span>Entry lifetime</span>
              <strong>{profile.entry_timeout} seconds</strong>
            </div>
          </div>
          <button
            onClick={() => {
              form.reset({
                ...profile,
                ...(profile.stock_units !== undefined
                  ? { stock_units: profile.stock_units ?? 1000 }
                  : {}),
                name: `${profile.name} copy`,
                id: mutationId(),
              });
              setEditing(true);
            }}
          >
            Customize a copy
          </button>
          {!["smoke", "qualified", "stock_smoke", "stock_qualified"].includes(
            profile.id,
          ) && (
            <button
              onClick={() => {
                form.reset(profile);
                setEditing(true);
              }}
            >
              Revise this profile
            </button>
          )}
        </>
      )}
      {editing && (
        <form
          onSubmit={form.handleSubmit(async (values) => {
            setBusy(true);
            try {
              const { version: _version, ...payload } = values;
              void _version;
              const result = await api<RiskProfile>(
                "/risk-profiles",
                "POST",
                payload,
              );
              setProfiles(await api("/risk-profiles"));
              setSelected({ id: result.id, version: result.version });
              preference("riskProfile", {
                id: result.id,
                version: result.version,
              });
              setEditing(false);
              notify(
                "Risk profile published. Existing authorizations keep their original limits.",
              );
            } catch (error) {
              notify((error as Error).message, true);
            } finally {
              setBusy(false);
            }
          })}
        >
          <label>
            Profile name
            <input
              {...form.register("name", { required: true, maxLength: 100 })}
            />
          </label>
          <div className="ws-form-grid">
            {simulation && (
              <label>
                Crypto units per run
                <input
                  type="number"
                  min="0.00000001"
                  max="10"
                  step="0.00000001"
                  {...form.register("quantity", {
                    required: true,
                    min: 0.00000001,
                    max: 10,
                  })}
                />
              </label>
            )}
            {(
              [
                ...(!simulation
                  ? [
                      ...(form.watch("stock_units") !== undefined
                        ? [
                            {
                              key: "stock_units",
                              label: "Maximum legal lots per run",
                              max: 1000,
                            } as const,
                          ]
                        : [
                            {
                              key: "shares",
                              label: "Shares per run",
                              max: 10,
                            } as const,
                          ]),
                    ]
                  : []),
                {
                  key: "runs",
                  label: "Concurrent runs",
                  max: simulation ? 2 : 5,
                },
                {
                  key: "entry_timeout",
                  label: "Entry lifetime (seconds)",
                  max: 30,
                },
              ] as const
            ).map(({ key, label, max }) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min={1}
                  max={max}
                  {...form.register(key, {
                    required: true,
                    valueAsNumber: true,
                    min: 1,
                    max,
                  })}
                />
              </label>
            ))}
            {(
              [
                {
                  key: "planned_stop_risk",
                  label: "Planned stop risk / run (USD)",
                  max: 10,
                },
                { key: "notional", label: "Notional / run (USD)", max: 1000 },
              ] as const
            ).map(({ key, label, max }) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  max={max}
                  {...form.register(key, { required: true, min: 0.01, max })}
                />
              </label>
            ))}
          </div>
          {Object.keys(form.formState.errors).length > 0 && (
            <p role="alert">
              Complete every field within its displayed limits.
            </p>
          )}
          <div className="ws-inline-actions">
            <button type="submit" disabled={busy}>
              Publish profile
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              Cancel edit
            </button>
          </div>
        </form>
      )}
      <p className="ws-muted">
        Account-wide ceilings remain {simulation ? "two" : "five"} distinct
        symbols, $50 reserved stop risk and $5,000 gross exposure. Strategy
        limits can be tighter. Gaps can exceed planned stop risk.
      </p>
      {!simulation && (
        <details>
          <summary>Internal paper qualification</summary>
          <Badge tone={qualification.verified_build ? "success" : "warning"}>
            {qualification.verified_build
              ? "Automated build gate passed"
              : "Automated build gate required"}
          </Badge>
          <p>
            First complete a supervised one-share entry, verify its broker-held
            protection, close it, and reconcile. The service records broker
            evidence separately from automated test results.
          </p>
          <ul>
            {Object.entries(
              (qualification.broker_evidence ?? {}) as Record<string, Json>,
            )
              .filter(([, value]) => value === true)
              .map(([key]) => (
                <li key={key}>{key.replaceAll("_", " ")}: observed</li>
              ))}
          </ul>
          <label className="ws-checkbox">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(event) => setReviewed(event.target.checked)}
            />
            I reviewed the paper evidence and accepted the
            configuration/recovery walkthrough. For unattended trials, I also
            verified the external outage alert.
          </label>
          <div className="ws-inline-actions">
            <button
              disabled={!reviewed || busy}
              onClick={() => void accept("supervised")}
            >
              Accept supervised expansion
            </button>
            <button
              disabled={!reviewed || busy}
              onClick={() => void accept("unattended")}
            >
              Accept unattended trial
            </button>
          </div>
          <p className="ws-muted">
            Acceptance never bypasses data, reconciliation, partial-fill
            protection, monitoring or backup checks. Five consecutive accepted
            sessions remain the final paper release requirement.
          </p>
          <h3>Session acceptance</h3>
          <p>
            {String(qualification.consecutive_accepted ?? 0)} of 5 consecutive
            exchange sessions accepted.
          </p>
          {((qualification.sessions ?? []) as Record<string, Json>[]).map(
            (session) => (
              <div key={String(session.date)} className="ws-banner">
                <strong>{String(session.date)}</strong>
                <span>
                  {session.accepted
                    ? "Accepted"
                    : session.eligible
                      ? "Ready for operator review"
                      : "Incomplete or blocked"}{" "}
                  · {String(session.runs ?? 0)} runs
                </span>
                {session.eligible === true && session.accepted !== true && (
                  <button
                    disabled={!reviewed || busy}
                    onClick={() => {
                      setBusy(true);
                      void api(
                        `/operations/qualification/sessions/${session.date}`,
                        "POST",
                        { confirmed: true },
                      )
                        .then(() =>
                          api<Record<string, Json>>(
                            "/operations/qualification",
                          ),
                        )
                        .then(setQualification)
                        .catch((error) => notify(String(error), true))
                        .finally(() => setBusy(false));
                    }}
                  >
                    Accept session: no unresolved defects or unexplained orders
                  </button>
                )}
              </div>
            ),
          )}
        </details>
      )}
      <p className="ws-muted">
        Daily P/L is informational. There is no cumulative daily-loss entry
        stop.
      </p>
      {profiles.some((p) => p.daily_loss !== undefined) && (
        <details>
          <summary>Historical profiles</summary>
          {profiles
            .filter((p) => p.daily_loss !== undefined)
            .map((p) => (
              <p key={`${p.id}:${p.version}`}>
                {p.name} - v{p.version}: daily-loss limit {money(p.daily_loss)}{" "}
                is retired and unenforced. Select its replacement for new
                authorizations.
              </p>
            ))}
        </details>
      )}
    </Panel>
  );
}
