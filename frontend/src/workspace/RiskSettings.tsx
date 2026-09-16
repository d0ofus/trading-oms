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
  shares: number;
  runs: number;
  planned_stop_risk: string;
  notional: string;
  daily_loss: string;
  entry_timeout: number;
};
export const chosenProfile = () =>
  readPreference("riskProfile", { id: "smoke", version: 1 });

export function RiskSettings({
  notify,
}: {
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
      shares: 1,
      runs: 1,
      planned_stop_risk: "10",
      notional: "1000",
      daily_loss: "100",
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
      title="3. Set paper limits"
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
          {profiles.map((item) => (
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
              <span>Share ceiling</span>
              <strong>{profile.shares} per run</strong>
            </div>
            <div>
              <span>Planned stop risk</span>
              <strong>{money(profile.planned_stop_risk)} / run</strong>
            </div>
            <div>
              <span>Notional ceiling</span>
              <strong>{money(profile.notional)} / run</strong>
            </div>
            <div>
              <span>Daily loss stop</span>
              <strong>{money(profile.daily_loss)}</strong>
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
                name: `${profile.name} copy`,
                id: mutationId(),
              });
              setEditing(true);
            }}
          >
            Customize a copy
          </button>
          {!["smoke", "qualified"].includes(profile.id) && (
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
            {(
              [
                { key: "shares", label: "Shares per run", max: 10 },
                { key: "runs", label: "Concurrent runs", max: 5 },
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
                { key: "daily_loss", label: "Daily loss stop (USD)", max: 100 },
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
        Account-wide ceilings remain five distinct symbols, $50 reserved stop
        risk and $5,000 gross exposure. Strategy limits can be tighter. Gaps can
        exceed planned stop risk.
      </p>
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
          I reviewed the paper evidence and accepted the configuration/recovery
          walkthrough. For unattended trials, I also verified the external
          outage alert.
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
                        api<Record<string, Json>>("/operations/qualification"),
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
    </Panel>
  );
}
