import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  exchangeTime,
  localTime,
  money,
  mutationId,
  policyLabel,
  type ArmPreview,
  type Contract,
  type Run,
  type Version,
} from "./api";
import { Modal, Readiness } from "./components";
import { useArmPolling } from "./useArmPolling";
import { PreparationForm } from "./PrepareRun";
import type { RiskProfile } from "./RiskSettings";

export function ArmReview({
  preview,
  selectRuns,
  setPreview,
  notify,
  refresh,
  navigate,
  contracts,
  connection,
}: {
  preview: ArmPreview | null;
  selectRuns: (ids: string[], replacedIds?: string[]) => void;
  setPreview: (value: ArmPreview | null) => void;
  notify: (message: string, error?: boolean) => void;
  refresh: () => Promise<void>;
  navigate: (path: string) => void;
  contracts: Contract[];
  connection?: string;
}) {
  const localProtection = preview?.runs.some(
    (r) => r.protection_type === "locally_monitored",
  );
  const simulation = preview?.environment === "live_crypto_simulation";
  const sessionTime = (stamp?: string | null) =>
    (simulation ||
      preview?.session_policy === "utc_24x7" ||
      preview?.session_policy?.startsWith("stock:")) &&
    stamp
      ? new Date(stamp).toUTCString()
      : exchangeTime(stamp);
  const [profiles, setProfiles] = useState<RiskProfile[]>([]);
  const [busy, setBusy] = useState(false);
  const [preparing, setPreparing] = useState<{
    run: Run;
    version: Version;
  } | null>(null);
  const reviewRequest = useRef<AbortController | null>(null);
  const open = Boolean(preview);
  useEffect(() => {
    if (!open) {
      reviewRequest.current?.abort();
      setPreparing(null);
    }
    const hidden = () => {
      if (document.hidden) reviewRequest.current?.abort();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      reviewRequest.current?.abort();
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [open]);
  const {
    unavailable,
    recheck,
    cancel: cancelPolling,
  } = useArmPolling(preview, setPreview, busy || !!preparing);
  const fingerprint =
    preview?.review_fingerprint ?? preview?.runs.map((r) => r.id).join(",");
  const actionId = useMemo(() => mutationId(), [fingerprint]);
  const replacement = preview?.policy_replacement;
  const earlierPolicies =
    replacement?.items.filter((item) => item.needs_replacement) ?? [];
  const replacementFingerprint = JSON.stringify(
    earlierPolicies.map((i) => [
      i.run_id,
      i.binding_hash,
      i.action,
      i.replacement_state,
    ]),
  );
  const replacementActionId = useMemo(
    () => mutationId(),
    [fingerprint, replacementFingerprint],
  );
  const restoring = earlierPolicies.some((i) => i.action === "restore");
  const stock = preview?.runs.every((r) => r.binding?.execution_plan);
  const fx = preview?.runs.every(
    (r) => r.binding?.execution_plan?.family === "spot_fx",
  );
  const fundingPolicies = [
    ...new Set(
      preview?.runs
        .map((r) => r.binding?.execution_plan?.funding_policy)
        .filter(Boolean),
    ),
  ];
  const brokerCredit = fundingPolicies.length > 0;
  const brokerDecision = fundingPolicies.includes("paper_buying_power_v1");
  const ceiling = (...values: (string | number | null | undefined)[]) => {
    const limits = values.filter((v) => v != null).map(Number);
    return limits.length ? money(Math.min(...limits)) : "No ceiling";
  };
  const stockLocal = preview?.runs.some(
    (r) =>
      r.binding?.execution_plan && r.protection_type === "locally_monitored",
  );
  const nativePrice = (runId: string, value: string | undefined) => {
    const binding = preview?.runs.find((run) => run.id === runId)?.binding;
    return money(
      value,
      binding?.contract.currency,
      binding?.execution_plan?.rules.price_scale,
    );
  };
  const recoveries = preview?.recoveries ?? [];
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void api<RiskProfile[]>(
      "/risk-profiles",
      "GET",
      undefined,
      controller.signal,
    )
      .then((items) =>
        setProfiles(items.filter((p) => p.daily_loss === undefined)),
      )
      .catch((error: Error) => {
        if (!controller.signal.aborted) notify(error.message, true);
      });
    return () => controller.abort();
  }, [open, notify, preview?.limits.id, preview?.limits.version]);
  async function review(
    profileId: string,
    version: number,
    unattended: boolean,
    sessionDate = preview?.session_date,
  ) {
    if (!preview) return;
    cancelPolling();
    reviewRequest.current?.abort();
    const request = new AbortController();
    reviewRequest.current = request;
    setBusy(true);
    try {
      const result = await api<ArmPreview>(
        "/runs/arm-preview",
        "POST",
        {
          ids: preview.runs.map((r) => r.id),
          profile_id: profileId,
          profile_version: version,
          unattended,
          session_date: sessionDate,
        },
        request.signal,
      );
      if (!request.signal.aborted) setPreview(result);
    } catch (error) {
      if (!request.signal.aborted) notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function reviewRuns(ids: string[], signal?: AbortSignal) {
    if (!preview) return;
    const next = await api<ArmPreview>(
      "/runs/arm-preview",
      "POST",
      {
        ids,
        profile_id: preview.limits.id,
        profile_version: preview.limits.version,
        unattended: preview.authorization === "unattended_paper_session",
        session_date: preview.flexible_session
          ? preview.session_date
          : undefined,
      },
      signal,
    );
    if (!signal?.aborted) {
      selectRuns(
        ids,
        preview.runs.map((r) => r.id),
      );
      setPreview(next);
    }
  }
  async function replacePolicy() {
    if (!preview || !replacement?.eligible || busy) return;
    cancelPolling();
    reviewRequest.current?.abort();
    const request = new AbortController();
    reviewRequest.current = request;
    setBusy(true);
    try {
      const result = await api<{ review_ids: string[] }>(
        "/runs/policy-replacement",
        "POST",
        {
          ids: preview.runs.map((run) => run.id),
          expected_binding_hashes: Object.fromEntries(
            preview.runs.map((run) => [run.id, run.binding?.hash]),
          ),
          target_policy_revision: replacement.target_policy_revision,
          target_execution_policy_revision:
            replacement.target_execution_policy_revision,
          mutation_id: replacementActionId,
          action: restoring ? "restore" : "adopt",
          expected_replacement_states: Object.fromEntries(
            earlierPolicies
              .filter((i) => i.action === "restore")
              .map((i) => [i.replacement_id, i.replacement_state]),
          ),
        },
        request.signal,
      );
      if (request.signal.aborted) return;
      await reviewRuns(result.review_ids, request.signal);
      await refresh();
      if (!request.signal.aborted)
        notify(
          "Current-policy replacement selected. Review and authorize it when ready. The original run is unchanged.",
        );
    } catch (error) {
      if (!request.signal.aborted) {
        notify((error as Error).message, true);
        recheck();
      }
    } finally {
      setBusy(false);
    }
  }
  async function reviewPreparation(run: Run) {
    cancelPolling();
    reviewRequest.current?.abort();
    const request = new AbortController();
    reviewRequest.current = request;
    setBusy(true);
    try {
      const version = await api<Version>(
        `/strategies/${run.strategy_id}/versions/${run.version}`,
        "GET",
        undefined,
        request.signal,
      );
      if (!request.signal.aborted) setPreparing({ run, version });
    } catch (error) {
      if (!request.signal.aborted) notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={!!preview}
      onOpenChange={(open) => {
        if (!open) {
          reviewRequest.current?.abort();
          setPreparing(null);
          setPreview(null);
        }
      }}
      title={
        preparing
          ? "Prepare strategy run"
          : simulation
            ? "Review simulation-session authorization"
            : "Review paper-session authorization"
      }
      description="Every selected run must pass final server validation. An armed session permits only the reviewed versions and limits."
      wide
    >
      {preview && preparing ? (
        <PreparationForm
          key={preparing.run.id}
          initialRun={preparing.run}
          version={preparing.version}
          contracts={contracts}
          connection={connection}
          notify={notify}
          close={() => setPreparing(null)}
          prepared={async (run) => {
            const request = new AbortController();
            reviewRequest.current = request;
            setBusy(true);
            try {
              await reviewRuns(
                preview.runs.map((r) =>
                  r.id === preparing.run.id ? run.id : r.id,
                ),
                request.signal,
              );
              await refresh();
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : (
        preview && (
          <>
            {earlierPolicies.length > 0 && (
              <section aria-label="Execution policy update">
                <p>
                  <strong>
                    {preview.runs.some(
                      (r) => r.binding?.execution_plan?.funding_policy,
                    )
                      ? "This selection includes an earlier funding or FX candle execution policy."
                      : "This run uses the earlier cash-only execution policy."}
                  </strong>
                </p>
                <p>
                  Use current broker buying-power checks and healthy quiet-feed
                  authorization. The replacement preserves the reviewed
                  strategy, quantity, route and protection. Your original run
                  and history remain available.
                </p>
                {earlierPolicies.map((item) => (
                  <div key={item.run_id}>
                    {item.blockers.map((reason) => (
                      <p role="alert" key={reason}>
                        {reason}
                      </p>
                    ))}
                    {item.replacement_id && (
                      <p>
                        {item.action === "restore"
                          ? "The archived, unused current-policy run can be restored without changing its binding or authorizing execution."
                          : "An existing linked replacement will be reused if unchanged."}
                      </p>
                    )}
                    {item.blockers.length > 0 && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void reviewPreparation(
                            preview.runs.find((run) => run.id === item.run_id)!,
                          )
                        }
                      >
                        Review preparation
                      </button>
                    )}
                  </div>
                ))}
                <button
                  disabled={busy || unavailable || !replacement?.eligible}
                  onClick={() => void replacePolicy()}
                >
                  {restoring
                    ? "Restore current-policy run"
                    : "Use current execution policy"}
                </button>
              </section>
            )}
            <details>
              <summary>Advanced execution policy</summary>
              <p>
                A risk profile controls permitted quantity, capacity and
                execution limits; it does not change the strategy's signals.
              </p>
              <div className="ws-form-grid">
                {preview.flexible_session && (
                  <label>
                    Trading date (New York)
                    <input
                      type="date"
                      value={preview.session_date ?? ""}
                      disabled={busy}
                      onChange={(event) => {
                        if (event.target.value)
                          void review(
                            preview.limits.id,
                            preview.limits.version,
                            preview.authorization ===
                              "unattended_paper_session",
                            event.target.value,
                          );
                      }}
                    />
                  </label>
                )}
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
                    {profiles
                      .filter(
                        (p) =>
                          (p.risk_policy ?? null) ===
                            (preview.limits.risk_policy ?? null) &&
                          (fx
                            ? p.fx_units !== undefined
                            : p.stock_units !== undefined) ===
                            Boolean(
                              preview.runs.every(
                                (r) => r.binding?.execution_plan,
                              ),
                            ),
                      )
                      .map((p) => (
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
                    <option
                      value={
                        simulation
                          ? "supervised_simulation_session"
                          : "supervised_paper_session"
                      }
                    >
                      {simulation
                        ? "Supervised simulation session"
                        : "Supervised paper session"}
                    </option>
                    {!simulation && !stock && (
                      <option value="unattended_paper_session">
                        Unattended paper trial
                      </option>
                    )}
                  </select>
                </label>
              </div>
            </details>
            {preview.runs.map((run) => (
              <div key={run.id}>
                {run.binding?.execution_plan && (
                  <p className="ws-muted">
                    {policyLabel(run)} | Run {run.id.slice(0, 8)}
                  </p>
                )}
                <strong>
                  {run.symbol} | Contract ID {run.conid}
                  {run.binding?.contract.currency &&
                    ` | ${run.binding.contract.currency}`}
                </strong>
                <p>
                  {run.protection_type === "locally_monitored"
                    ? run.binding?.execution_plan
                      ? "Locally monitored protection | cannot execute while the application or connection is unavailable."
                      : "Locally monitored protection | unavailable while this application or connection is down. Initial crypto qualification ceiling: $25."
                    : "Broker-held protection"}
                </p>
                {run.binding?.execution_plan ? (
                  <p>
                    Effective entry ceiling (USD):{" "}
                    {ceiling(
                      run.binding.sizing.notional,
                      preview.limits.notional,
                    )}{" "}
                    | Planned stop-risk ceiling (USD):{" "}
                    {ceiling(
                      run.binding.sizing.risk,
                      preview.limits.planned_stop_risk,
                    )}{" "}
                    | Sizing: {run.binding.sizing.sizing} |{" "}
                    {fx
                      ? `Reviewed quantity (${run.binding.contract.symbol})`
                      : "Reviewed shares"}
                    :{" "}
                    {fx
                      ? `${run.binding.sizing.quantity} ${run.binding.contract.symbol}`
                      : run.binding.sizing.shares}
                    {" | Published entries per authorization: "}
                    {preview.summaries?.find((s) => s.run_id === run.id)
                      ?.document.settings.max_entries ?? "See published rules"}
                  </p>
                ) : run.binding ? (
                  <p>
                    Reviewed sizing:{" "}
                    {Object.entries(run.binding.sizing)
                      .filter(
                        ([key]) =>
                          run.protection_type !== "locally_monitored" ||
                          (key !== "shares" && key !== "sizing"),
                      )
                      .map(([key, value]) => `${key}: ${value}`)
                      .join(" | ")}
                  </p>
                ) : null}
                {run.binding?.execution_plan &&
                  preview.checks
                    .filter(
                      (c) =>
                        (c.code === `stock_${run.id}` ||
                          c.code === `fx_funding_${run.id}`) &&
                        c.passed,
                    )
                    .map((c) => (
                      <p key={c.code}>Indicative amounts: {c.detail}</p>
                    ))}
                {run.capability_error && (
                  <p role="alert">{run.capability_error}</p>
                )}
                {fx && (
                  <p role="note">
                    {run.binding?.execution_plan?.signal_source} signals, strict
                    breakout above{" "}
                    {run.binding?.execution_plan?.policy ===
                    "idealpro_broker_candles_v2"
                      ? "the immediately preceding completed IBKR candle; its latest completed minute is available immediately after authorization"
                      : "the prior complete live minute after authorization"}
                    . BUY MKT/IOC;
                    {run.binding?.execution_plan?.funding_policy
                      ? " broker-checked currency quantity. "
                      : " funded currency quantity with no intentional borrowing. "}
                    Protection uses actual fill VWAP × 0.99 and bid/ask
                    triggers. The 1% distance is not a guaranteed loss limit.
                    Local stop exits use limit orders at fresh bids, with
                    cancellation and reconciliation before any retry. Market
                    entry cost and exit fills are not guaranteed.
                  </p>
                )}
                {run.binding?.execution_plan?.session_mode ===
                  "premarket_regular" && (
                  <p role="note">
                    Pre-market + regular hours: whole-share limit entry at the
                    fresh ask; no entry chasing. Locally monitored 1% stop
                    triggers limit exits at fresh bids. Unfilled exits are
                    cancelled and repriced only after confirmation and
                    reconciliation. The stop trigger is not a guaranteed loss
                    limit; retries can sell materially below it. No after-hours
                    execution.
                  </p>
                )}
              </div>
            ))}
            {preview.crypto_entries?.map((entry) => (
              <p key={entry.run_id}>
                <strong>
                  Effective paper cash ceiling: {money(entry.cash_ceiling)}
                </strong>{" "}
                | MKT IOC buy | 1% locally monitored protection
              </p>
            ))}
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
                <strong>{sessionTime(preview.entry_cutoff)}</strong>
                <small>{localTime(preview.entry_cutoff)}</small>
              </div>
              <div>
                <span>Authorization expires</span>
                <strong>{sessionTime(preview.expires_at)}</strong>
                <small>{localTime(preview.expires_at)}</small>
              </div>
              <div>
                <span>
                  {stock ? "Risk-profile ceilings (USD)" : "Per-run ceilings"}
                </span>
                <strong>
                  {fx
                    ? "Selected base-currency quantity"
                    : preview.limits.stock_units !== undefined
                      ? preview.limits.stock_units === null
                        ? "Contract-aware quantity"
                        : `${preview.limits.stock_units} legal lot`
                      : localProtection
                        ? "Cash budget"
                        : `${preview.limits.quantity ?? preview.limits.shares} ${simulation ? "units" : "shares"}`}{" "}
                  · {ceiling(preview.limits.planned_stop_risk)} planned stop
                  risk
                </strong>
                <small>
                  {ceiling(preview.limits.notional)} notional ·{" "}
                  {simulation
                    ? "local simulated protection"
                    : localProtection
                      ? "locally monitored protection"
                      : "broker-held GTC protection"}
                </small>
              </div>
            </div>
            {preview.paired_entries?.map((pair) => (
              <section
                key={pair.run_id}
                className="ws-config-section"
                aria-label="Paired entry review"
              >
                <div>
                  <h3>Previous-minute OCA breakout</h3>
                  <p>{pair.status}</p>
                  {pair.prices && (
                    <dl className="ws-facts">
                      <dt>Source candle</dt>
                      <dd>{localTime(pair.candle)}</dd>
                      <dt>Buy stop-market</dt>
                      <dd>
                        {nativePrice(pair.run_id, pair.prices.long_entry)}
                      </dd>
                      <dt>Short sell stop-market</dt>
                      <dd>
                        {nativePrice(pair.run_id, pair.prices.short_entry)}
                      </dd>
                      <dt>Quantity per branch</dt>
                      <dd>{pair.quantity} units</dd>
                      <dt>Combined pending reservation</dt>
                      <dd>
                        {money(pair.reservation?.risk)} planned risk ·{" "}
                        {money(pair.reservation?.notional)} notional
                      </dd>
                    </dl>
                  )}
                  <p>
                    Fixed 1% stop from the actual average fill. First fill
                    cancels the opposite entry. Refresh each minute after
                    confirmed cancellation; one trade then pause.
                  </p>
                  {pair.hypothetical_short && (
                    <p>
                      Short positions are hypothetical local simulation; no
                      Paxos orders or borrow model.
                    </p>
                  )}
                </div>
              </section>
            ))}
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
            {recoveries.length > 0 && (
              <section aria-label="Verified incident recovery">
                <h3>Recovered — acknowledgment required</h3>
                <p>
                  These restrictions apply to shared services or the selected
                  runs. Other paused runs remain paused. Emergency stop is a
                  separate control.
                </p>
                <p>
                  Recovery uses current engine, watchdog, order and account
                  evidence appropriate to each concern. These checks run again
                  on confirmation.
                </p>
                {recoveries.map((item) => (
                  <p key={`${item.id}:${item.revision}`}>
                    Verified {item.code ?? item.id} recovery: {item.scope?.type}{" "}
                    {item.scope?.key === "*" ? "" : item.scope?.key}.{" "}
                    {item.recovery_detail}
                  </p>
                ))}
                <p>
                  The final authorization explicitly acknowledges these verified
                  recoveries. Any remaining investigation stays open; recovery
                  does not establish that an unknown root cause was fixed.
                </p>
              </section>
            )}
            {stockLocal && (
              <p role="note">
                By authorizing, you acknowledge that locally monitored
                protection depends on this application, the broker connection
                and fresh market data. The stop distance is a trigger, not a
                guaranteed loss limit.
              </p>
            )}
            {preview.resume_policy && (
              <p role="note">
                This authorization may resume after verified routine
                connectivity or transient feed recovery in this engine session.
                Old triggers expire. Restart, manual disarm, account changes or
                uncertain orders/protection require fresh review.
              </p>
            )}
            {unavailable && (
              <p role="alert">
                Current readiness is unavailable. Authorization is disabled
                until a successful refresh.
              </p>
            )}
            {brokerCredit && (
              <p role="note">
                This authorization permits broker-approved borrowing when native
                cash is insufficient. Financing costs may apply. Buying power is
                checked automatically before entry.{" "}
                {brokerDecision
                  ? "This policy does not require a credit preview. IBKR determines whether the exact paper order is acceptable and may reject it despite the account-level precheck."
                  : "A credit preview does not guarantee acceptance."}
                {fx &&
                  " Healthy quiet FX feeds remain armed while waiting for fresh observations and the reference required by the reviewed execution policy."}
              </p>
            )}
            <Readiness
              checks={preview.checks
                .filter((c) => !c.passed || c.stable)
                .map((c) =>
                  c.code === "incidents" && preview.eligible_after_recovery_ack
                    ? {
                        ...c,
                        remediation: null,
                        detail:
                          "Verified recoveries are included in this final authorization.",
                      }
                    : c,
                )}
              navigate={navigate}
            />
            <details>
              <summary>
                Readiness details (
                {preview.checks.filter((c) => c.passed && !c.stable).length}{" "}
                passed)
              </summary>
              <Readiness
                checks={preview.checks.filter((c) => c.passed && !c.stable)}
              />
            </details>
            <div className="ws-modal-actions">
              <button onClick={() => setPreview(null)}>Back to desk</button>
              <button disabled={busy} onClick={recheck}>
                Refresh readiness
              </button>
              <button
                className="ws-primary"
                disabled={
                  !(preview.eligible || preview.eligible_after_recovery_ack) ||
                  busy ||
                  unavailable
                }
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api("/runs/arm", "POST", {
                      ids: preview.runs.map((r) => r.id),
                      mutation_id: actionId,
                      session_date: preview.flexible_session
                        ? preview.session_date
                        : undefined,
                      review_fingerprint: preview.review_fingerprint,
                      resume_policy: preview.resume_policy,
                      ...(brokerCredit
                        ? {
                            funding_policy_acknowledged:
                              fundingPolicies.length === 1
                                ? fundingPolicies[0]
                                : fundingPolicies,
                          }
                        : {}),
                      ...(fx
                        ? {
                            fx_policy_revision: Array.from(
                              new Set(
                                preview.runs.map(
                                  (run) =>
                                    run.binding?.execution_plan?.policy ??
                                    "idealpro_funded_fx_v1",
                                ),
                              ),
                            ),
                          }
                        : {}),
                      review_instance: preview.review_instance,
                      local_protection_acknowledged: Boolean(stockLocal),
                      execution_plan_revisions: Object.fromEntries(
                        preview.runs
                          .filter((r) => r.binding?.execution_plan)
                          .map((r) => [r.id, r.binding!.execution_plan!.hash]),
                      ),
                      recovery_acknowledgments: recoveries.map((item) => ({
                        id: item.id,
                        revision: item.revision,
                      })),
                      profile_id: preview.limits.id,
                      profile_version: preview.limits.version,
                      unattended:
                        preview.authorization === "unattended_paper_session",
                    });
                    setPreview(null);
                    await refresh();
                    notify(
                      simulation
                        ? "Reviewed local simulation session armed."
                        : "Reviewed paper session armed.",
                    );
                  } catch (error) {
                    notify((error as Error).message, true);
                    recheck();
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {simulation
                  ? "Arm selected simulation session"
                  : recoveries.length
                    ? "Acknowledge verified recoveries & arm paper run"
                    : stockLocal
                      ? "Acknowledge local protection & arm paper run"
                      : "Arm selected paper session"}
              </button>
            </div>
          </>
        )
      )}
    </Modal>
  );
}
