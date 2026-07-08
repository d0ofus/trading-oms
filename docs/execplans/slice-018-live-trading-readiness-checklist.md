# ExecPlan: Slice 018 Live Trading Readiness Checklist

## 1. Goal

Add a structured, auditable live-trading readiness gate that proves live trading remains disabled
and records exactly which readiness evidence is missing before any future consideration.

## 2. Non-goals

- Live trading.
- Enabling live trading configuration.
- Broker order submission.
- Real broker credentials, account IDs, certificates, private keys, passwords, tokens, or secrets.
- IBKR SDK dependency.
- Socket or network transport.
- Changing the default paper/simulation posture.
- Production rollout.

## 3. Safety constraints

- Do not enable live trading.
- Do not add any code path that can transmit a live or paper broker order.
- Do not add credentials, account IDs, passwords, certificates, private keys, tokens, or secrets.
- `Settings` must continue to reject truthy `LIVE_TRADING_ENABLED` values.
- Readiness evaluation must be audit-friendly and must not itself authorize live trading.
- Missing readiness evidence must block readiness.
- Even a fully satisfied checklist must remain a review artifact, not an execution switch.

## 4. Current state

The backend already has strict `Settings` defaults and validation:

- `APP_MODE` is limited to `paper` or `simulation`;
- `LIVE_TRADING_ENABLED` defaults to `false` and is rejected when `true`;
- production requires simulation mode;
- IBKR account mode is paper-only.

`docs/LIVE_TRADING_READINESS_CHECKLIST.md` exists as a human-readable future checklist and says live
trading is not approved, but it is not represented as a typed/auditable backend model.

## 5. Proposed design

Add `trading_oms_backend.live_readiness` with:

- `LiveTradingReadinessEvidence`, a typed checklist matching the existing readiness document;
- `ReadinessCheckResult`, a structured per-item pass/fail record;
- `LiveTradingReadinessDecision`, an immutable decision record with explicit `not_ready` or
  `ready_for_final_review` status;
- `evaluate_live_trading_readiness`, which journals every readiness evaluation and always reports
  `live_trading_enabled: false`.

The evaluator will reject any request that tries to evaluate an enablement path. The checklist can
show all evidence collected, but it cannot flip configuration or submit orders.

## 6. Data model changes

No database tables or migrations.

New in-memory/domain records:

- `LiveTradingReadinessEvidence`
- `ReadinessCheckResult`
- `LiveTradingReadinessDecision`

## 7. API changes

No HTTP API, CLI command, config key, dependency, network endpoint, or persistence change.

The new backend module exposes local Python types and evaluator functions only.

## 8. Test plan

- Unit tests proving default/empty evidence evaluates to `not_ready` and journals a decision.
- Unit tests proving a single missing evidence item blocks readiness and is listed explicitly.
- Unit tests proving all checklist evidence can produce `ready_for_final_review` while still keeping
  live trading disabled and not authorized.
- Unit tests proving any requested live enablement path is rejected.
- Unit tests proving existing `Settings` still rejects truthy `LIVE_TRADING_ENABLED` values.
- Unit tests proving readiness payloads and source contain no credentials, network, broker SDK, or
  order-transmission behavior.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the slice branch changes to remove the live-readiness module, tests, docs, ExecPlan, and
Slice 018 status updates. No persistent data or external state is introduced.

## 11. Implementation steps

1. Add focused live-readiness tests.
2. Implement the local readiness model and evaluator.
3. Update the readiness checklist docs, configuration docs, README, roadmap/status docs, and slice
   status.
4. Run verification and repair failures.
5. Self-review and red-team the readiness boundary.

## 12. Completion criteria

- Live-trading readiness gate remains disabled by default.
- Missing readiness evidence blocks readiness.
- Readiness status is explicit and auditable.
- Tests cover not-ready behavior and forbidden enablement paths.
- Verification passes.
- No live broker connectivity or order submission path is added.
- No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are
  introduced.

## 13. Risks and assumptions

- This slice is a readiness/audit artifact, not permission for live trading.
- Future production rollout still requires explicit human approval and external review.
- Emergency-stop implementation remains a future gap unless already proven by later slices.
