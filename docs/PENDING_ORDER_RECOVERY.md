# Pending paper orders and recovery

`ApiPending` is a known IBKR status: TWS/Gateway has not yet sent the order to the
IB server. `PendingSubmit` also awaits acknowledgment. Neither status is a rejection,
a fill, or verified protection. See [IBKR's order-status documentation](https://interactivebrokers.github.io/tws-api/order_submission.html).

The paper workspace keeps these orders in `dispatching`, displays **Awaiting broker
acknowledgment**, retains their risk reservations, and does not resubmit. A pending
cash-budget buy can report zero filled and remaining quantities; these values do not
mean that it completed. Owned quantity comes from durable execution records.

The default entry deadline is still 30 seconds from creation. If no terminal outcome
arrives by then, the application requests cancellation. It retains uncertainty and
the reservation until reconciliation establishes the outcome. A partial fill still
counts as the trade and receives protection based on its actual entry price. A late
execution after cancellation is retained and reconciled, never discarded.

## Inspect an attempt

On **Trading Desk**, inspect **Orders & executions**. Select an order to see the
broker status, whether full crypto order identity has been verified, confirmed fills,
and any recorded application cancellation reason. **Run & order history → Browse
records** retains access after a terminal order leaves the active list.

**Awaiting complete broker order details** means a status callback arrived before
full contract, account-context and order information. Reconciliation remains blocked;
the UI does not report this missing evidence as a proven identity mismatch. Supplied
details that contradict the intent remain a failure. An identity label is descriptive
evidence, not an independent permission to trade.

Delayed pending callbacks cannot move acknowledged, cancelling or terminal orders
backward. Contradictory working/terminal observations require a fresh completed-order
snapshot and full reconciliation. Releasing the resulting incident still requires
explicit operator review. Duplicate callbacks remain in the audit without duplicate
state transitions or execution fills.

Application cancellation reasons distinguish operator action, entry deadline, disarm,
emergency stop and incident restriction. Older cancellation records may lack a reason;
they are labelled accordingly rather than rewritten or attributed to broker permissions.

## Recover an attempt cancelled by the former ApiPending bug

1. Stop the old application normally and start the updated checkout with
   `.\scripts\start-workspace.ps1`. The launcher rebuilds the frontend. Refresh the
   browser; do not remove the existing state directory or journal.
2. Connect and verify the paper context, then allow complete order, execution and
   position reconciliation. Check the order details and TWS executions for any fills.
3. In **Activity**, review the relevant incident. Only acknowledge once current recovery
   evidence permits release. Notes are optional. Emergency stop remains separate.
4. Return to the Desk and explicitly **Review & arm** the run. The old attempt is not
   resent. Wait for a newly completed eligible live minute and a subsequent fresh
   breakout through its high. Market-data readiness alone does not trigger an order.
5. Watch the order status, confirmed executions and locally monitored stop. Keep the
   initial $25 ceiling; qualification requires a real paper entry/protection/exit and
   reconciled-flat cycle. Offline tests do not prove PAXOS paper availability.

This correction does not automatically release historical restrictions, clear emergency
stop, arm a strategy, or change published strategies and financial limits. All normal
paper-only, freshness, approval and risk controls still apply.

## Broker rejection (201) after a valid trigger

A real code 201 rejection is different from pending acknowledgment. The adapter now
classifies ordinary and advanced rejection explanations into bounded, generated
diagnostics. Raw broker text, account identifiers and advanced rejection JSON are
never retained. Unknown or ambiguous explanations remain explicitly unavailable;
inspect that order's rejection explanation in TWS before another attempt.

The order inspector and incident review show the safe reason and originating order.
The latest broker status is separate from rejection evidence. For example, a rejected
buy followed by Cancelled displays **Broker rejected entry — no fill; final broker
status: Cancelled** only after current reconciliation establishes no executions.
Late or partial executions still establish ownership and receive normal protection.
The existing rejected-exit retry guard also uses this retained rejection evidence:
a later Cancelled callback cannot turn a rejected exit into an automatic retry.

One owned order/leg failure produces one correlated incident. Inactive followed by
201 refines that incident; duplicate callbacks remain journaled without increasing
the failure count or restarting the healthy interval. New uncertainty after broker
progress and contradictory outcomes still invalidate recovery. The restriction
remains workspace-wide and requires dedicated recovery review, current reconciliation,
30 healthy seconds, then explicit acknowledgment. Recovery does not establish that
IBKR will accept another order. Re-arm manually and wait for a new live candle.

Keep **Global Configuration → API → Settings → Show advanced order reject in UI
always** unchecked to receive advanced rejection details through the API. This
setting affects diagnostic delivery, not broker eligibility. Do not add automatic
rejection overrides, increase the $25 qualification budget, or change routing solely
because of code 201. See [IBKR advanced rejection documentation](https://interactivebrokers.github.io/tws-api/order_submission.html).

On the first updated startup, the application backs up existing state before adding
incident correlation indexing. Historical journal entries, approvals, strategy hashes
and existing incident payloads are unchanged. Old duplicate incidents retain their
normal separate review requirements; their missing explanations cannot be recovered
from the numeric error code. No incident is automatically released by the update.
