# Automatic recovery, quiet FX authorization and broker credit

New stock and FX runs prepared by the current interface pin `broker_credit_v1`.
New FX runs also pin `quiet_fx_v1`. Existing published strategies need no conversion
or republication to adopt these execution policies: prepare a **new run** and review
its final authorization. Existing runs retain their original funding and data terms.
Execution remains IBKR paper only. The canvas, nodes, connections, page structure and
prepare → review → arm sequence are unchanged.

Older runs now show **Use current execution policy** inside their authorization review.
This prepares and selects a linked replacement in the same dialog; the final arm action
remains required. No strategy copy or republication is needed. The published version,
exact base-currency quantity (including 0.01 AUD), route, session, signal source, optional
limits and protection method are preserved. Original bindings, approvals and history
remain unchanged, and the original run is not archived automatically.

Replacement requires the source to be disarmed, flat and free of outstanding orders,
reservations, protection and exit work. Past broker activity additionally requires fresh
successful reconciliation. Repeated requests reuse an unchanged inactive replacement.
Changed contract requirements produce a specific blocker and **Review preparation**, which
opens the existing form with the original selections. The application never resizes the
quantity or changes route/protection to make replacement pass.

If that linked replacement was archived without ever submitting an order, the same
review offers **Restore current-policy run**. Restoration requires its unchanged binding,
current compatibility, flat/disarmed state and no reservations or outstanding operations.
It preserves the original archive record and appends an authenticated restoration event.
It restores visibility only: no authorization, incident release or emergency-stop release.
Replaying an earlier creation request cannot undo a later archive. Changed or previously
used replacements remain blocked with **Review preparation** available.

Adoption/restoration updates both the review and the Desk's saved selection and inspected
run. This selection survives closing review, navigation and browser reload, including runs
prepared from Studio or Testing. Existing rows and reviews show **Earlier cash-only policy**
or **Current execution policy** with a short run ID so identical strategy names are clear.

After installing a verified build, restart the workspace normally and reload the browser.
Review the original AUD.USD run, choose **Restore current-policy run** if offered, and check
that the review shows **Current execution policy**, **Broker buying power and quantity**
and the unchanged quantity. Final authorization remains a separate explicit action.

## What the operator sees

- A healthy, established FX subscription with complete required history may be
  authorized while prices are quiet. The Desk then shows the armed run waiting for
  fresh selected-source and bid/ask observations. Unknown/rejected streams still block.
- FX review rows keep their positions when freshness changes. Automatic waiting does
  not show **Resolve**. **Broker buying power and quantity** reports waiting for quote
  evidence when the price-dependent calculation cannot yet run.
- **FX feed and history** reports established subscription/history health independently
  of execution freshness. A healthy quiet feed remains green with neutral **Waiting for
  fresh MIDPOINT and bid/ask** or **Waiting for a complete live minute** text. Failed or
  unknown streams remain visible; the separate underlying dispatch checks are unchanged.
- The older **Funded base-currency quantity** message describes the bound cash-only
  policy. Missing fresh cash evidence is not proof of insufficient funds or a broker
  credit refusal. Current-policy reviews show **Broker buying power and quantity**;
  automatic account/credit work is neutral, while actual credit blockers link to Settings.
- The one final authorization includes permission to use broker-approved borrowing
  when native cash is insufficient. Financing costs may apply. No extra checkbox.
- Before entry, source and receipt timestamps must still be within 15 seconds, quotes
  valid and uncrossed, and the signal based on a new complete eligible live minute.
  No historical candles, watchlist snapshots or interrupted crossings create entries.

Quiet data is not an incident. Genuine failures retain their recovery evidence.

The FX Market data badge now reports **Feed live** for established healthy timestamped
streams. Session and history have separate status. Execution text can neutrally report
**Waiting for clock alignment**, **Waiting for fresh observations**, **Waiting for a complete
live minute**, or **Ready for the next qualifying signal**. A green feed badge is not
permission to submit an order. Stream rejections, invalid quotes and continuity faults
remain visible immediately.

FX observations separate structural validity from timing. Source/receipt freshness and
displayed signed ages use one evaluation instant. A slightly ahead-of-local-clock source
observation, within the existing five-second clock-health bound, waits in a bounded live
buffer (4,096 observations per contract). It is processed once, in source order, only after
alignment and while its original receipt remains within 15 seconds. Pending values never
authorize funding/dispatch or trigger local protection. Generation changes, retirement,
expiry and supersession discard unusable observations; overflow and larger clock offsets
raise genuine feed restrictions. Ages ahead of the clock are displayed explicitly.

After authorization/resumption, the reference candle must begin after the authorization
time plus the five-second clock uncertainty. Historical bars and buffered observations
from a previous connection cannot become entry signals. A buffered crossing whose signal
minute has expired is discarded, with signal-window validation repeated before reservation
and immediately before dispatch. An unused MIDPOINT stream cannot reset a Bid/Ask strategy.
Signed arrival offsets, bounded
counters and the latest 32 timing transitions are available in data diagnostics; journal
timing summaries are limited to one per stream per minute rather than logging every quote.

Routine recoveries complete automatically after 30 healthy seconds in the background.
After current post-failure reconciliation proves no dependency remains, unused feed
restrictions retire immediately, without a healthy-feed observation interval. A paused,
flat, unsubscribed run alone is not a dependency. A virtual CASH-pair position alone
does not establish currency ownership; actual allocations, unresolved orders,
reservations and protection/exit work do.

Only complete engine-fault episodes matching the allowlisted corrected history-request
fingerprint can recover automatically, after a verified corrective build, reconciliation
and stability checks. Missing/mixed diagnostics and other faults retain explicit review.
Released/retired history is preserved. Emergency stop remains separately released.
Restart never restores entry authorization.

## Funding and credit evidence

The shared policy applies to all supported reusable stock templates/custom graphs and
the supported FX long-only strategy. It uses usable native settled cash where sufficient.
Otherwise it waits for the paper adapter's isolated What-If credit response. The account
type label alone is never borrowing permission. Quantity rules, fees, published optional
ceilings and five-run capacity remain enforced. No automatic resizing, currency-conversion
order, route change or rejection override is introduced.

Account evidence includes currency-aware available funds, initial/maintenance margin,
equity with loan value and excess liquidity. Availability and liabilities use the
appropriate conservative conversion side. Reservations account for incremental margin
and fees; a complete post-dispatch broker snapshot prevents reserving reflected margin
twice. Outstanding fee allowances remain reserved. Any adverse account change invalidates
affected evidence; routine snapshot refresh preserves the last valid complete snapshot.
Fully settled-cash purchases do not require unused margin fields: their complete cost
and fees remain reserved against native funds and account availability. Missing margin
fields can never authorize borrowing or a short sale.

The account preview queue coalesces identical economic terms and favors authorized runs,
then least-recently-requested work. At most one What-If request starts per minute, including
legacy short previews; pacing survives restart. Review reads never send requests directly.
Idle unarmed runs do not keep refreshing previews. Estimates are tied to current account
revision, engine/connection context, contract, approved plan, quantity, side, type/TIF,
route and limit/stop price. Market-order estimates do not guarantee the execution cost.

Single-entry credit evidence expires after 30 seconds. Opposing OCA branches use a
180-second maximum to permit sequential account-paced previews, with both exact economic
terms and the account revision still matching. Absolute GTD timestamps are not reusable
signal permission: fresh session/deadline checks enforce the current trigger's expiry at
dispatch. Changed branch prices require new evidence. A paced or slow preview may cause a
signal to be skipped. No expired crossing is replayed or order automatically resent.

What-If always sets `whatIf=True` inside the paper adapter and uses distinct request IDs.
Responses must match the request and contain finite, usable margin evidence. The preview
is cancelled after review, and timeout/old-generation responses cannot authorize entries.
Broker warnings are classified into generated explanations; raw warnings/account IDs are
not persisted. [IBKR describes this credit-preview mechanism and its pacing guidance](https://www.interactivebrokers.com/docs/tws-api/doc/orders/test-order-impact-what-if).

Expected negative currency balances from actual approved margin fills are reconciled
against the execution/commission ledger. Negative cash alone is not an incident. Unexplained
cash changes, missing commissions or broker-reported buying-power shortfalls still hold
new entries. Cash balance updates alone cannot prove an interest/financing adjustment;
unexplained differences remain held until evidence is available. Protection and requested
risk-reducing exits do not depend on new-entry credit approval.

## Deployment and rollback

Run `scripts/verify.ps1`, then restart the workspace normally. The first policy installation
and additive incident-policy migration back up state before writing. Prepare new runs to
adopt the new terms; previously prepared runs are never silently changed.

- `OMS_DISABLE_BROKER_CREDIT_ARM=1` blocks new credit-policy authorizations/entries.
- `OMS_DISABLE_POLICY_REPLACEMENT=1` disables new inline replacements. It does not alter
  any existing run or protection. Replacement installation backs up state before the
  first link/receipt is written; changes and operator identity are audited transactionally.
- `OMS_DISABLE_CORRECTED_FAULT_RECOVERY=1` disables the narrow engine-fault auto-release.
- Existing automatic-recovery and authorization-resume rollback switches still apply.

These switches retain management of existing positions, protection, exits and history.
Automated fixture tests cannot qualify the actual account's margin permissions. The
separate execution acceptance remains an operator-armed natural paper signal compared
with TWS; no forced trade is part of the verification gate.
