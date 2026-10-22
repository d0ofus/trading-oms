# Minimal paper-stock workflow

Current monitoring and recovery behavior is defined in [Current operational monitoring](CURRENT_OPERATIONAL_MONITORING.md). It supersedes the historical recovery intervals and acknowledgment workflow described below.

This policy uses live IBKR data and **paper execution only**. Studio keeps the same
drag-and-drop nodes, connections, parameters, positions and published signal semantics.
No quote snapshot or historical download can create an execution signal.

## Prepare, review, authorize

Select a published strategy and exact resolved instrument, enter a legal quantity,
and choose session and protection. Instrument search is also available inside preparation.
The authenticated preparation coordinator starts paper-context validation, subscription,
required history, FX and reconciliation. Explicit Disconnect is respected. Unsupported
broker/exchange requirements are explained; there is no contract-rule questionnaire.

Preparation opens the existing authorization review directly. Technical successes are
collapsed under Readiness details. The review refreshes every two seconds, with one
request in flight, and stops on hide/close. Waiting for a fresh trade is a readiness
condition, not an incident that needs acknowledgment. A failed refresh disables approval.

One final action authorizes the displayed instrument, quantity, session, protection,
entry/exit method and published trade limit. For local protection that action explicitly
acknowledges application, connection and fresh-data dependence. A stop distance is a
trigger, not a guaranteed loss limit. Applicable dedicated recoveries may join this
action only after all their evidence requirements pass. Emergency stop stays separate.

## Risk profiles and schema 8

A risk profile is an immutable execution policy, separate from the graph's signal logic.
New schema-8 stock templates default to fixed, explicit share quantities and `null`
notional/stop-risk ceilings. Optional positive ceilings have no former USD 1,000/10
maximum. Risk sizing still requires a positive stop-risk budget. An illegal or
unaffordable explicit quantity is rejected, never silently reduced.

- **Paper stock — selected quantity**, version 2: up to five active runs, no policy
  monetary ceilings. The former aggregate USD 5,000 exposure and USD 50 stop-risk caps
  do not apply to this new policy.
- **Paper stock — one-lot qualification**, version 2: optional one-lot restriction,
  one active run. It is not a mandatory qualification step.

Newly prepared runs use [broker-aware cash or margin funding](BROKER_CREDIT_AND_QUIET_FX.md).
Existing cash-only bindings retain the following original-policy terms.

Native settled funds, conservative fresh FX, fees, active reservations, legal entry
and exit quantities, ownership and protection still constrain each order. Actual
notional, estimated stop risk and exposure remain journaled. Lower optional published
limits continue to apply. No automatic borrowing, FX conversion or rerouting is added.

Schemas 3–7 and existing profile versions retain their limits, hashes and behavior.
Use the explicit optional-ceiling upgrade on an editable stock draft, change its
limits, publish, and prepare a new run to adopt schema 8. Existing positions retain
their original protection contract. Immutable successor profiles and first schema-8
writes back up state before their additive migration.

## Gate inventory

| Check | Handling | Principal implementation |
|---|---|---|
| Paper login and handshake | Automatic adapter verification, no human checkbox | `preparation.py`, `broker.py` |
| Contract, route, rules, schedules, required data/FX | Automatic preparation; exact selection for ambiguity | `preparation.py`, `stock_engine.py`, `stock_rules.py` |
| Reconciliation, ownership and protection | Automatic staged snapshots; Recheck remains diagnostic | `reconciliation.py`, `engine.py`, `oms.py` |
| Session, history, trade/source and bid/ask freshness | Run-aware automatic arming/dispatch checks; 15 seconds retained | `data_views.py`, `premarket.py`, `stock_engine.py` |
| Quantity, cash, fees, optional ceilings/reservations | Automatic at sizing, reservation and adapter boundaries | `paper_risk.py`, `stock_policy.py`, `store.py`, `broker_stocks.py` |
| Verification build, watchdog, clock, callback integrity | Automatic; genuine failures block | `engine.py`, `verification.py` |
| Routine recovery | Automatic verified release and dependency retirement | `incident_recovery.py` |
| Dedicated recovery and local protection | Explicit terms in the final arming action | `engine.py`, `ArmReview.tsx` |
| Emergency stop | Separate explicit release; never part of routine recovery | `engine.py` |
| Strategy publication | Explicit, immutable version | `store.py`, `Studio.tsx` |

The same evidence paths serve review, confirmation, recovery and dispatch with
stage-specific requirements. Dispatch always rechecks current evidence. Successful
subscription or What-If evidence is not a promise of broker acceptance.

## Reconciliation and data

The last complete, verified snapshot remains usable during an ordinary refresh only
within its freshness window and valid account/connection/state revision. Pending
positions, orders and funds are collected separately. A complete snapshot replaces
them together. Request and connection generations fence stale callbacks. A submission,
execution, cancellation or discrepancy invalidates affected evidence immediately.
A snapshot superseded by a trading-state change must be collected again.

Pre-market cards use their run's approved session and history requirements. Completed
extended history is independent of regular-history coverage. Sampled Last and actual
execution trade remain separate. A quiet interval may retain authorization while
waiting, but stale observations cannot arm a new run or dispatch an entry. Rolling
schedule dates and retrieval timestamps do not change a binding's material policy.

## Recovery and existing authorizations

Routine recovery retains current watchdog identity/health, verified paper context,
post-failure reconciliation, required dependency restoration and 30 healthy seconds.
Healthy startup without a recovery episode adds no stability delay. A broad service
hold can release with a failed dependency only after a contract-scoped hold contains
that failure. Unused feed retirement requires no run/exposure/order/exit dependency.

Only newly reviewed approvals explicitly pinning `same_engine_routine_v1` may resume
after known connectivity/service or classified transient/pacing feed interruptions.
They retain counters, remaining limits and reservations, require the same engine and
verified account context, and must be unexpired. Old triggers are discarded; a new
eligible live evaluation is required. Unknown or interrupted submissions are never
resent. Terminal zero-fill and completed-trade pause semantics remain in force.

Restart, manual disconnect/disarm, emergency stop, account change, watchdog/engine
integrity failure, callback overflow, invalid data continuity and order/protection
uncertainty revoke entry permission. They require fresh review. Established protection
and requested risk-reducing exits recover independently; an outage does not liquidate.

Dedicated recoveries keep their evidence requirements and open investigations. Final
authorization checks exact episode revisions and a material review fingerprint, then
records releases and authorization transactionally and idempotently. Optional notes
remain optional. An operational recovery does not assert that an unknown cause is fixed.

## Rollback and acceptance

`OMS_DISABLE_MINIMAL_PAPER_ARM=1` disables new-policy arming.
`OMS_DISABLE_PAPER_RESUME=1` disables automatic entry resumption. Existing stock and
pre-market rollback flags also remain available. These do not remove ownership,
position monitoring, protection or requested exits. Database restore requires a stopped
engine and reconciled broker exposure; never overwrite a running journal.

Run `./scripts/verify.ps1`. Automated tests use isolated stores/fake transports and
browser fixtures; no broker execution is needed for them. Broker acceptance needs a
separate operator-armed paper observation of a natural signal, comparing order,
execution, protection and reconciliation with TWS. Do not force a trade to pass a test.
