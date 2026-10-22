import { useState } from "react";
import {
  api,
  type Contract,
  type StockRules,
  type StockCompatibility,
} from "./api";

export function StockRulesEditor({
  contract,
  saved,
  notify,
  compatibility,
  protection = "broker_held",
  paired = false,
}: {
  contract: Contract;
  saved: () => void;
  notify: (message: string, error?: boolean) => void;
  compatibility?: StockCompatibility | null;
  protection?: string;
  paired?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [rules, setRules] = useState<StockRules>(
    contract.stock_rules ?? {
      revision: 0,
      source: "operator_verified",
      reference: "TWS contract details",
      calendar: "",
      currency: contract.currency ?? "",
      quantity_increment: "",
      minimum_quantity: "",
      exit_increment: "",
      price_scale: "",
      fee_reserve: "",
      same_day_resale: false,
      broker_protection: false,
      native_oca: false,
      local_protection: false,
      fractional_protection: false,
    },
  );
  const automatic = contract.stock_rules?.reference === "US share policy v1";
  return (
    <details>
      <summary>Advanced contract rules</summary>
      {automatic && (
        <p>
          US whole-share conventions were populated from documented policy and
          broker metadata. This is not proof of account acceptance or paper
          qualification.
        </p>
      )}
      {automatic && (
        <label>
          Reusable fee allowance per branch ({contract.currency}) — funding
          reserve, not a commission quote
          <input
            id="stock-rule-fee_reserve"
            value={rules.fee_reserve}
            onChange={(e) =>
              setRules({ ...rules, fee_reserve: e.target.value })
            }
          />
          <button
            disabled={busy || rules.fee_reserve === ""}
            onClick={async () => {
              setBusy(true);
              try {
                await api(
                  `/contracts/${contract.conid}/fee-allowance`,
                  "POST",
                  {
                    amount: rules.fee_reserve,
                    revision: compatibility?.fee_policy?.revision ?? 0,
                  },
                );
                saved();
              } catch (e) {
                notify((e as Error).message, true);
              } finally {
                setBusy(false);
              }
            }}
          >
            Save reusable allowance
          </button>
        </label>
      )}
      <p>
        Verify these values in TWS contract details or the exchange
        specification. Unknown values cannot authorize execution.
        Broker-reported minimum: {contract.min_size ?? "unavailable"};
        increment: {contract.size_increment ?? "unavailable"}. A reported
        increment may differ from a board lot.
      </p>
      <div className="ws-form-grid">
        {(
          [
            ["calendar", "Exchange calendar (e.g. XHKG or XNYS)"],
            ["minimum_quantity", "Minimum entry quantity"],
            ["quantity_increment", "Entry quantity increment / board lot"],
            ["exit_increment", "Verified partial-fill exit increment"],
            ["price_scale", "Native currency units per quoted price unit"],
            ["fee_reserve", `Fee allowance per branch (${contract.currency})`],
          ] as const
        )
          .filter(([key]) => !automatic || key !== "fee_reserve")
          .map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                id={`stock-rule-${key}`}
                value={String(rules[key])}
                onChange={(e) => setRules({ ...rules, [key]: e.target.value })}
              />
            </label>
          ))}
      </div>
      <label>
        Evidence reference for manual overrides
        <select
          value={
            rules.reference === "US share policy v1"
              ? "TWS contract details"
              : rules.reference
          }
          onChange={(e) => setRules({ ...rules, reference: e.target.value })}
        >
          <option>TWS contract details</option>
          <option>Exchange specification</option>
          <option>IBKR contract search</option>
        </select>
      </label>
      {(
        [
          ["same_day_resale", "Same-day resale is permitted"],
          [
            "broker_protection",
            "Broker stops and partial / odd-lot exits are supported",
          ],
          [
            "native_oca",
            "Native protected OCA with overfill protection is supported",
          ],
          [
            "local_protection",
            "Local stop monitoring and partial / odd-lot broker exits are supported",
          ],
          [
            "fractional_protection",
            "The entire entry, protection and exit workflow supports fractional shares",
          ],
        ] as const
      )
        .filter(
          ([key]) =>
            key === "same_day_resale" ||
            (key === "broker_protection" && protection === "broker_held") ||
            (key === "native_oca" && paired) ||
            (key === "local_protection" &&
              protection === "locally_monitored") ||
            (key === "fractional_protection" &&
              Math.min(
                Number(rules.quantity_increment),
                Number(rules.exit_increment),
              ) < 1),
        )
        .map(([key, label]) => (
          <label className="ws-checkbox" key={key}>
            <input
              id={`stock-rule-${key}`}
              type="checkbox"
              checked={rules[key]}
              onChange={(e) => setRules({ ...rules, [key]: e.target.checked })}
            />
            {label}
          </label>
        ))}
      <p>
        These are recorded operator checks, not proof of broker acceptance.
        Updating rules invalidates existing entry approvals; existing positions
        retain their approved protection plan.
      </p>
      <button
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void api(`/contracts/${contract.conid}/stock-rules`, "POST", {
            rules: {
              ...rules,
              reference:
                rules.reference === "US share policy v1"
                  ? "TWS contract details"
                  : rules.reference,
              revision: rules.revision + 1,
              source: "operator_verified",
            },
          })
            .then(() => {
              setRules({ ...rules, revision: rules.revision + 1 });
              saved();
            })
            .catch((error: Error) => notify(error.message, true))
            .finally(() => setBusy(false));
        }}
      >
        Record verified rules
      </button>
    </details>
  );
}
