import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Contract,
  type Run,
  type Version,
  type StockCompatibility,
} from "./api";
import { ContractSearch } from "./ContractSearch";
import { usePageVisible } from "./useArmPolling";
import { Modal } from "./components";

export function contractLabel(c: Contract) {
  return [
    c.symbol,
    c.sec_type,
    c.currency,
    c.routing_exchange ?? c.exchange,
    c.primary_exchange,
    c.expiry,
    c.strike,
    c.right,
    c.multiplier ? `× ${c.multiplier}` : null,
    `ID ${c.conid}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

type PreparationProps = {
  initialRun?: Run;
  simulation?: boolean;
  connection?: string;
  version: Version;
  contracts: Contract[];
  close: () => void;
  prepared: (run: Run) => Promise<void>;
  notify: (message: string, error?: boolean) => void;
};

export function PrepareRun(props: PreparationProps) {
  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) props.close();
      }}
      title="Prepare strategy run"
      description="Select the exact contract and review sizing. This binding is immutable; arming is a separate approval."
    >
      <PreparationForm
        key={`${props.version.strategy_id}:${props.version.version}`}
        {...props}
      />
    </Modal>
  );
}

export function PreparationForm({
  initialRun,
  version,
  contracts,
  close,
  prepared,
  notify,
  simulation = false,
  connection,
}: PreparationProps) {
  const visible = usePageVisible();
  const creationRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    const hidden = () => {
      if (document.hidden) creationRequest.current?.abort();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      creationRequest.current?.abort();
      document.removeEventListener("visibilitychange", hidden);
    };
  }, []);
  const fx = version.document.schema_version === 9;
  const stock = [7, 8, 9].includes(version.document.schema_version);
  const modern = [8, 9].includes(version.document.schema_version);
  const generic = stock || version.document.schema_version === 6;
  const [compatibility, setCompatibility] = useState<StockCompatibility | null>(
    null,
  );
  const [protection, setProtection] = useState(
    initialRun?.protection_type ?? "broker_held",
  );
  const [sessionMode, setSessionMode] = useState(
    fx
      ? "fx"
      : (initialRun?.binding?.execution_plan?.session_mode ?? "regular"),
  );
  const [compatibilityError, setCompatibilityError] = useState("");
  const [preparationDetail, setPreparationDetail] = useState("");
  const reviewedInputs = useRef("");
  const [rulesRevision, setRulesRevision] = useState(0);
  const kind = version.document.nodes.some((n) => n.kind === "long_breakout")
    ? stock
      ? "stock_breakout"
      : "crypto_breakout"
    : version.document.nodes.some((n) => n.kind === "paired_stop")
      ? "oca_breakout"
      : "long_bracket";
  const [conid, setConid] = useState(
    initialRun ? String(initialRun.conid) : "",
  );
  const [found, setFound] = useState<Contract[]>([]);
  const [searching, setSearching] = useState(false);
  const [shares, setShares] = useState(
    String(initialRun?.binding?.sizing[fx ? "quantity" : "shares"] ?? "1"),
  );
  const [sharesEdited, setSharesEdited] = useState(Boolean(initialRun));
  const [notional, setNotional] = useState(
    String(
      (initialRun?.binding
        ? initialRun.binding.sizing.notional
        : version.document.settings.notional) ?? "",
    ),
  );
  const [risk, setRisk] = useState(
    String(
      (initialRun?.binding
        ? initialRun.binding.sizing.risk
        : version.document.settings.risk) ?? "",
    ),
  );
  const [busy, setBusy] = useState(false);
  const available = [
    ...contracts,
    ...found.filter(
      (c) => !contracts.some((existing) => existing.conid === c.conid),
    ),
  ].filter(
    (c) =>
      c.resolved !== false &&
      (generic || c.symbol === version.document.settings.symbol),
  );
  const contract = available.find((c) => c.conid === Number(conid));
  const preparationLease = useMemo(
    () => ({ id: crypto.randomUUID(), conid, sessionMode, visible }),
    [conid, sessionMode, visible],
  );
  useEffect(
    () => () => {
      if (preparationLease.conid)
        void api("/runs/prepare-context/release", "POST", {
          lease_id: preparationLease.id,
        }).catch(() => undefined);
    },
    [preparationLease],
  );
  useEffect(() => {
    if (!stock || !conid || !visible) return;
    const timer = window.setTimeout(() => setRulesRevision((v) => v + 1), 2000);
    return () => window.clearTimeout(timer);
  }, [stock, conid, compatibility, visible]);
  useEffect(() => {
    const inputs = JSON.stringify([
      version.strategy_id,
      version.version,
      conid,
      protection,
      sessionMode,
      shares,
      notional,
      risk,
    ]);
    if (inputs !== reviewedInputs.current) {
      setCompatibility(null);
      reviewedInputs.current = inputs;
    }
    setCompatibilityError("");
    if (!stock || !conid || !visible) return;
    const controller = new AbortController();
    void api<{ status: string; detail: string }>(
      "/runs/prepare-context",
      "POST",
      {
        strategy_id: version.strategy_id,
        version: version.version,
        conid: Number(conid),
        session_mode: sessionMode,
        ...(fx ? { execution_policy: "idealpro_broker_candles_v2" } : {}),
        lease_id: preparationLease.id,
      },
      controller.signal,
    )
      .then((progress) => {
        if (!controller.signal.aborted) setPreparationDetail(progress.detail);
        return api<StockCompatibility>(
          "/runs/compatibility",
          "POST",
          {
            strategy_id: version.strategy_id,
            version: version.version,
            conid: Number(conid),
            protection_type: protection,
            funding_policy: "paper_buying_power_v1",
            ...(fx ? { execution_policy: "idealpro_broker_candles_v2" } : {}),
            session_mode: sessionMode,
            sizing: {
              ...(fx ? { quantity: shares } : { shares }),
              notional: modern && !notional ? null : notional,
              risk: modern && !risk ? null : risk,
              sizing: version.document.settings.sizing,
            },
          },
          controller.signal,
        );
      })
      .then((value) => {
        if (!controller.signal.aborted) {
          setCompatibility(value);
          if (!sharesEdited && value.rules?.minimum_quantity)
            setShares(value.rules.minimum_quantity);
        }
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setCompatibilityError(error.message);
      });
    return () => controller.abort();
  }, [
    stock,
    fx,
    modern,
    visible,
    conid,
    protection,
    sessionMode,
    shares,
    sharesEdited,
    notional,
    risk,
    version.document.settings.sizing,
    rulesRevision,
    preparationLease.id,
    version.strategy_id,
    version.version,
    notify,
  ]);
  const compatible = stock
    ? Boolean(
        contract &&
        compatibility &&
        (compatibility.can_prepare ?? !compatibility.blockers.length),
      )
    : contract &&
      !(kind === "crypto_breakout" && contract.sec_type === "STK") &&
      ((simulation && !generic) ||
        !contract.capabilities ||
        contract.capabilities.executions.includes(kind));
  return (
    <>
      <p>
        <strong>IBKR Paper</strong> · {version.name} v{version.version}
        {fx
          ? " · Reusable IDEALPRO FX strategy"
          : stock
            ? " · Reusable stock strategy"
            : kind === "crypto_breakout"
              ? " · Legacy crypto definition"
              : " · Legacy definition"}
      </p>
      <label>
        Resolved instrument
        <select
          value={conid}
          onChange={(e) => {
            setConid(e.target.value);
            setSharesEdited(false);
            const selected = contracts.find(
              (c) => c.conid === Number(e.target.value),
            );
            if (stock)
              setShares(selected?.stock_rules?.minimum_quantity ?? "1");
          }}
        >
          <option value="">Select an exact contract</option>
          {available.map((c) => (
            <option key={c.conid} value={c.conid}>
              {contractLabel(c)}
            </option>
          ))}
        </select>
      </label>
      {stock && (
        <details onToggle={(event) => setSearching(event.currentTarget.open)}>
          <summary>Find another instrument</summary>
          {searching && (
            <>
              <button
                disabled={connection === "connected"}
                onClick={() =>
                  void api("/workspace/session/connect", "POST").catch(
                    (e: Error) => notify(e.message, true),
                  )
                }
              >
                Connect paper Gateway
              </button>
              <ContractSearch
                snapshot={{
                  connection: connection ?? "disconnected",
                  contracts: available,
                  data: [],
                }}
                busy={busy}
                action={(path, body) => api(path, "POST", body)}
                selectContract={(selected) => {
                  setFound([selected]);
                  setConid(String(selected.conid));
                  setSharesEdited(false);
                }}
              />
            </>
          )}
        </details>
      )}
      {stock && conid && preparationDetail && (
        <small role="status">{preparationDetail}</small>
      )}
      {!available.length && (
        <p>
          Find and select the exact instrument here to start automatic
          preparation.
        </p>
      )}
      {contract && !stock && (
        <p>
          {contract.capabilities?.session_policy === "utc_24x7"
            ? "UTC daily session, including weekends"
            : "Regular US equity session"}{" "}
          ·{" "}
          {!compatible
            ? "Execution unavailable for this contract/template combination"
            : contract.capabilities?.protection_type === "locally_monitored"
              ? "Locally monitored protection — cannot execute while this application or connection is unavailable."
              : "Broker-held protection"}
        </p>
      )}
      {contract && !stock && !compatible && (
        <p role="alert">
          {kind === "crypto_breakout" && contract.sec_type === "STK"
            ? "This legacy crypto execution definition cannot trade stocks. In Studio, use Review & publish → Create reusable copy, then explicitly publish the stock copy. Duplicate preserves the original behavior."
            : kind === "oca_breakout" && contract.sec_type === "CRYPTO"
              ? "PAXOS does not support this opposing native-stop/short structure. Select the separate long-only breakout template."
              : (contract.capabilities?.unsupported_reason ??
                "This template cannot execute on this contract.")}
        </p>
      )}
      {stock && contract && (
        <>
          <p>
            {compatibility
              ? compatible
                ? compatibility.status === "compatible"
                  ? "Ready"
                  : "Ready for supervised qualification"
                : compatibility.resolution_status === "checking"
                  ? "Checking broker rules"
                  : compatibility.resolution_status === "budget_requirement"
                    ? "Budget/funding requirement"
                    : "Unsupported requirement"
              : "Checking broker rules…"}{" "}
            ·{" "}
            {fx
              ? `${contract.currency} per ${contract.symbol}`
              : `${contract.currency} prices`}{" "}
            / USD risk limits
          </p>
          {compatibility?.blockers.map((message) => (
            <p role="alert" key={message}>
              {message}
            </p>
          ))}
          <label>
            Trading session
            <select
              value={sessionMode}
              onChange={(e) => {
                setSessionMode(e.target.value);
                if (e.target.value === "premarket_regular")
                  setProtection("locally_monitored");
              }}
            >
              {fx ? (
                <option value="fx">
                  FX broker session — maintenance breaks excluded
                </option>
              ) : (
                <>
                  <option value="regular">Regular hours</option>
                  <option value="premarket_regular">
                    Pre-market + regular hours — long-only breakout
                  </option>
                </>
              )}
            </select>
          </label>
          {sessionMode === "premarket_regular" && (
            <p>
              Whole-share paper limit orders, with locally monitored 1%
              protection and fresh-bid exit retries. No after-hours execution.
              Limits may remain unfilled; approval is required.
            </p>
          )}
          <label>
            Protection method
            <select
              value={protection}
              onChange={(e) => setProtection(e.target.value)}
            >
              <option value="broker_held">Broker-held protection</option>
              <option value="locally_monitored">
                Locally monitored protection — explicit acknowledgment required
              </option>
            </select>
          </label>
          {compatibility?.rules && (
            <p>
              Minimum {compatibility.rules.minimum_quantity}{" "}
              {fx ? contract.symbol : "shares"}; entry increment{" "}
              {compatibility.rules.quantity_increment}; exit increment{" "}
              {compatibility.rules.exit_increment}.{" "}
              {fx
                ? "Qualified FX broker intervals"
                : `${compatibility.rules.calendar} liquid sessions`}
              . The smallest legal quantity must fit every approved limit.
            </p>
          )}
          <details>
            <summary>Automatic contract rules</summary>
            <p>
              Rules come from broker metadata and documented exchange policies.
              No manual verification form is required. Broker acceptance remains
              subject to the account and selected order structure.
            </p>
            {compatibility?.rules && (
              <p>
                {fx
                  ? `Base quantity: ${contract.symbol}; price: ${contract.currency} per ${contract.symbol}.`
                  : `Price scale: ${compatibility.rules.price_scale}.`}{" "}
                Funding fees are estimated automatically for the selected
                quantity.
              </p>
            )}
            {compatibility?.field_requirements?.map((f) => (
              <p key={f.field}>
                {f.field.replaceAll("_", " ")}:{" "}
                {f.available ? "Available" : "Unavailable for this workflow"}
              </p>
            ))}
          </details>
          <button type="button" onClick={() => setRulesRevision((v) => v + 1)}>
            Refresh broker rules
          </button>
        </>
      )}
      {generic && (
        <div className="ws-form-grid">
          {kind !== "crypto_breakout" &&
            (!stock || version.document.settings.sizing === "fixed") && (
              <label>
                {fx
                  ? `Quantity (${contract?.symbol ?? "base currency"})`
                  : kind === "oca_breakout"
                    ? "Shares per branch"
                    : "Shares"}
                <input
                  type="number"
                  min={
                    stock
                      ? (compatibility?.rules?.minimum_quantity ?? "0.000001")
                      : 1
                  }
                  step={
                    stock
                      ? (compatibility?.rules?.quantity_increment ?? "any")
                      : 1
                  }
                  max={stock ? undefined : 10}
                  value={shares}
                  onChange={(e) => {
                    setSharesEdited(true);
                    setShares(e.target.value);
                  }}
                />
              </label>
            )}
          <label>
            {kind === "crypto_breakout"
              ? "USD cash budget"
              : kind === "oca_breakout"
                ? "Combined notional ceiling (USD)"
                : "Entry notional ceiling (USD)"}
            <input
              type="number"
              min="0.01"
              max={
                version.document.settings.notional == null
                  ? undefined
                  : String(version.document.settings.notional)
              }
              placeholder={modern ? "No ceiling (optional)" : undefined}
              step="0.01"
              value={notional}
              onChange={(e) => setNotional(e.target.value)}
            />
          </label>
          <label>
            Planned stop risk (USD)
            <input
              type="number"
              min="0.01"
              max={
                version.document.settings.risk == null
                  ? undefined
                  : String(version.document.settings.risk)
              }
              placeholder={modern ? "No ceiling (optional)" : undefined}
              step="0.01"
              value={risk}
              onChange={(e) => setRisk(e.target.value)}
            />
          </label>
        </div>
      )}
      {stock && compatibility?.indicative_sizing && (
        <p role="status">
          Indicative quantity: {compatibility.indicative_sizing.quantity}{" "}
          {fx ? contract?.symbol : "shares"}· notional USD{" "}
          {Number(compatibility.indicative_sizing.notional_usd).toFixed(2)} ·
          planned stop risk{" "}
          {compatibility.indicative_sizing.stop_risk_usd
            ? `USD ${Number(compatibility.indicative_sizing.stop_risk_usd).toFixed(2)}`
            : "requires protective inputs"}{" "}
          · funding including allowance:{" "}
          {compatibility.indicative_sizing.currency}{" "}
          {Number(compatibility.indicative_sizing.native_funds).toFixed(2)}.
          Refreshed before arming and submission.
        </p>
      )}
      {stock &&
        compatibility?.arming_requirements?.map((reason) => (
          <p key={reason}>{reason}</p>
        ))}
      {compatibilityError && <p role="alert">{compatibilityError}</p>}
      {compatibility?.minimum_lot && (
        <p role="status">
          Minimum legal quantity: {compatibility.minimum_lot.quantity} shares.{" "}
          {compatibility.minimum_lot.currency}{" "}
          {Number(compatibility.minimum_lot.native_notional).toFixed(2)}{" "}
          notional ({Number(compatibility.minimum_lot.notional_usd).toFixed(2)}{" "}
          USD), plus {compatibility.minimum_lot.currency}{" "}
          {Number(compatibility.minimum_lot.fee_reserve).toFixed(2)} estimated
          funding fees. Total funding reserve:{" "}
          {compatibility.minimum_lot.currency}{" "}
          {Number(compatibility.minimum_lot.native_funds).toFixed(2)}.
          {compatibility.minimum_lot.stop_risk_usd && (
            <>
              {" "}
              Indicative stop risk: USD{" "}
              {Number(compatibility.minimum_lot.stop_risk_usd).toFixed(2)}.
            </>
          )}{" "}
          Published ceiling:{" "}
          {compatibility.minimum_lot.published_ceiling_usd ?? "None"} USD.
        </p>
      )}
      {stock && !compatible && (
        <div role="status">
          {!contract
            ? "Select a resolved instrument."
            : !compatibility
              ? compatibilityError || "Checking preparation requirements…"
              : (
                  compatibility.preparation_blockers ?? compatibility.blockers
                ).join(" ")}
        </div>
      )}
      {kind === "crypto_breakout" && (
        <p>
          One paper market buy, IOC. Initial supervised ceiling: $25. The 1%
          stop is calculated from actual fills and monitored locally. No
          automatic top-up or short sale. Paper availability is confirmed only
          by broker acceptance.
        </p>
      )}
      {fx && (
        <p>
          Signal: {String(version.document.settings.signal_source)}. A fresh
          signal strictly above the immediately preceding completed IBKR minute
          high submits one paper market buy, IOC. The 1% stop uses actual fills.
          No top-ups or automatic currency conversion.{" "}
          {compatibility?.plan?.funding_policy
            ? "Account buying power is checked automatically. Broker-permitted borrowing may be used; financing costs may apply. IBKR may reject an order despite this precheck. "
            : compatibility?.plan
              ? "This funding policy requires usable currency cash without intentional borrowing. "
              : "Funding terms will be shown with the qualified execution policy. "}
          Smaller orders can use IBKR’s smaller-order handling; acceptance and
          residual exits remain subject to broker capability.
        </p>
      )}
      <button
        className="primary"
        disabled={!compatible || busy}
        onClick={() => {
          creationRequest.current?.abort();
          const request = new AbortController();
          creationRequest.current = request;
          setBusy(true);
          void api<Run>(
            "/runs",
            "POST",
            {
              strategy_id: version.strategy_id,
              version: version.version,
              conid: Number(conid),
              ...(stock
                ? {
                    protection_type: protection,
                    execution_plan_revision: compatibility?.plan?.hash,
                    ...(fx
                      ? { execution_policy: "idealpro_broker_candles_v2" }
                      : {}),
                    ...(stock
                      ? { funding_policy: "paper_buying_power_v1" }
                      : {}),
                    session_mode: sessionMode,
                  }
                : {}),
              ...(generic
                ? {
                    sizing: {
                      ...(fx
                        ? { quantity: shares }
                        : { shares: stock ? shares : Number(shares) }),
                      notional: modern && !notional ? null : notional,
                      risk: modern && !risk ? null : risk,
                      sizing: version.document.settings.sizing,
                    },
                  }
                : {}),
            },
            request.signal,
          )
            .then(async (run) => {
              if (request.signal.aborted) return;
              close();
              await prepared(run);
            })
            .catch((error: Error) => {
              if (!request.signal.aborted) notify(error.message, true);
            })
            .finally(() => setBusy(false));
        }}
      >
        Prepare bound run
      </button>
    </>
  );
}
