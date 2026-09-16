import { useEffect, useState } from "react";
import {
  api,
  exchangeTime,
  localTime,
  money,
  mutationId,
  type ArmPreview,
} from "./api";
import { Modal, Readiness } from "./components";
import type { RiskProfile } from "./RiskSettings";

export function ArmReview({
  preview,
  setPreview,
  notify,
  refresh,
  navigate,
}: {
  preview: ArmPreview | null;
  setPreview: (value: ArmPreview | null) => void;
  notify: (message: string, error?: boolean) => void;
  refresh: () => Promise<void>;
  navigate: (path: string) => void;
}) {
  const [profiles, setProfiles] = useState<RiskProfile[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api<RiskProfile[]>("/risk-profiles")
      .then(setProfiles)
      .catch((error: Error) => notify(error.message, true));
  }, [notify]);
  async function review(
    profileId: string,
    version: number,
    unattended: boolean,
  ) {
    if (!preview) return;
    setBusy(true);
    try {
      setPreview(
        await api<ArmPreview>("/runs/arm-preview", "POST", {
          ids: preview.runs.map((r) => r.id),
          profile_id: profileId,
          profile_version: version,
          unattended,
        }),
      );
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={!!preview}
      onOpenChange={(open) => {
        if (!open) setPreview(null);
      }}
      title="Review paper-session authorization"
      description="Every selected run must pass final server validation. An armed session permits only the reviewed versions and limits."
      wide
    >
      {preview && (
        <>
          <div className="ws-form-grid">
            <label>
              Risk profile
              <select
                disabled={busy}
                value={`${preview.limits.id}:${preview.limits.version}`}
                onChange={(event) => {
                  const [id, version] = event.target.value.split(":");
                  void review(
                    id,
                    Number(version),
                    preview.authorization === "unattended_paper_session",
                  );
                }}
              >
                {profiles.map((p) => (
                  <option
                    key={`${p.id}:${p.version}`}
                    value={`${p.id}:${p.version}`}
                  >
                    {p.name} · v{p.version}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Session supervision
              <select
                disabled={busy}
                value={preview.authorization}
                onChange={(event) =>
                  void review(
                    preview.limits.id,
                    preview.limits.version,
                    event.target.value === "unattended_paper_session",
                  )
                }
              >
                <option value="supervised_paper_session">
                  Supervised paper session
                </option>
                <option value="unattended_paper_session">
                  Unattended paper trial
                </option>
              </select>
            </label>
          </div>
          <div className="ws-arm-summary">
            <div>
              <span>Selected runs</span>
              <strong>
                {preview.runs
                  .map((r) => `${r.symbol} · ${r.name} v${r.version}`)
                  .join(", ")}
              </strong>
            </div>
            <div>
              <span>New-entry cutoff</span>
              <strong>{exchangeTime(preview.entry_cutoff)}</strong>
              <small>{localTime(preview.entry_cutoff)}</small>
            </div>
            <div>
              <span>Authorization expires</span>
              <strong>{exchangeTime(preview.expires_at)}</strong>
              <small>{localTime(preview.expires_at)}</small>
            </div>
            <div>
              <span>Per-run ceilings</span>
              <strong>
                {preview.limits.shares} shares ·{" "}
                {money(preview.limits.planned_stop_risk)} planned stop risk
              </strong>
              <small>
                {money(preview.limits.notional)} notional · broker-held GTC
                protection
              </small>
            </div>
          </div>
          {preview.summaries?.map((version) => (
            <details key={version.run_id}>
              <summary>
                {version.name} · v{version.version} · entry and exit contract
              </summary>
              <ul>
                {version.explanation.map((item) => (
                  <li key={`${item.node}-${item.kind}`}>{item.text}</li>
                ))}
              </ul>
            </details>
          ))}
          <Readiness
            checks={preview.checks}
            navigate={(path) => {
              setPreview(null);
              navigate(path);
            }}
          />
          <div className="ws-modal-actions">
            <button onClick={() => setPreview(null)}>Back to desk</button>
            <button
              disabled={busy}
              onClick={() =>
                void review(
                  preview.limits.id,
                  preview.limits.version,
                  preview.authorization === "unattended_paper_session",
                )
              }
            >
              Refresh readiness
            </button>
            <button
              className="ws-primary"
              disabled={!preview.eligible || busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api("/runs/arm", "POST", {
                    ids: preview.runs.map((r) => r.id),
                    mutation_id: mutationId(),
                    profile_id: preview.limits.id,
                    profile_version: preview.limits.version,
                    unattended:
                      preview.authorization === "unattended_paper_session",
                  });
                  setPreview(null);
                  await refresh();
                  notify("Reviewed paper session armed.");
                } catch (error) {
                  notify((error as Error).message, true);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Arm selected paper session
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
