# Paper buying power and signal outcomes

New stock and IDEALPRO FX preparations bind `paper_buying_power_v1`. This supersedes the earlier cash-only and `broker_credit_v1` preview policies for new preparations; existing bindings retain their approved policy. Published strategy versions and hashes do not change.

## Entry assessment

The new policy requires a verified paper account, completed current reconciliation and account evidence no older than 30 seconds. It uses broker `BuyingPower`, with positive `AvailableFunds` and `ExcessLiquidity`. Missing evidence is automatic checking. Confirmed insufficient buying power or maintenance headroom is a specific blocker.

Proposed notional plus the existing fee allowance must fit unreserved Buying Power. Account capacity and allocations are normalized conservatively using current conversion evidence; responses also give the allocation in the account's valuation currency. Full notional is an **application buying-power allocation**, not an estimate of initial margin. Available Funds is not charged the full notional. Paired entries allocate both branches conservatively. Stock and FX entries share the transactional allocation check.

No positive native-currency cash or settled-cash balance is required. This policy does not request or require What-If previews. Broker-permitted borrowing may occur and financing costs may apply. IBKR decides whether the exact paper order is acceptable; headline buying power does not guarantee instrument-specific approval or a fill. Known permissions, legal quantity, route, order structure, shortability where required, protection, optional strategy ceilings and paper-only controls remain enforced.

Uncertain submissions retain allocations. Successful reconciliation begun after dispatch must positively establish the broker order before broker-reported capacity takes over; absence alone cannot release capacity. Outstanding fees remain reserved. Fills/account changes invalidate affected evidence. Protection and requested exits remain independent of new-entry capacity. Expected debit balances from approved borrowing are not automatically incidents; unexplained differences still require reconciliation.

## Adopt the policy

1. If the existing run is armed, use **Disarm strategy**. An armed binding cannot change.
2. Select the run and open **Review & arm**. Choose **Use current execution policy**. The replacement preserves the published strategy, exact quantity, contract, route, signal source, session and protection.
3. The Desk and review select the replacement and persist the selection. Check **Current execution policy**, its short run ID and **Broker buying power and quantity**. Make the existing final paper authorization when ready.

An archived, unused linked replacement requires the explicit restoration action. A `broker_credit_v1` replacement is not reused as the new revision. Original runs, approvals and history remain. No FX copy or republication is required. State is backed up before installing policy metadata.

AUD.USD's existing `0.01 AUD` stays exactly 0.01 base-currency units. It is not converted into a lot or increased. Broker refusal is reported accurately and never causes automatic resizing, rerouting or resubmission.

## Signal outcomes

Detection is committed before funding/dispatch checks, with the run/authorization, reference minute, high, crossing price/time, expiry and capture reference. One current record per run is retained; meaningful transitions stay in the append-only journal. The order link is committed with its allocation and intent before transmission.

Run details show the FX reference minute/high, selected signal price, strict comparison and latest outcome: checking account evidence, blocked with a reason, expired, submitted, broker rejected, partially filled or filled. Submitted signals follow their existing order rather than creating another entry.

The Desk distinguishes **Armed — waiting for breakout**, **Signal detected — checking account**, and **Entry blocked: [reason]**. The header reports actual armed runs and the selected runs' required inputs. A flat run's broker-held protection label explains that its plan is approved and the stop is submitted for confirmed fills.

The 15-second source/receipt limits, complete post-authorization live minute, strict FX `>` comparison and expiry remain. History, restart and the previously missed crossing cannot submit an entry. Ordinary waiting does not create an incident.

## Rollback and acceptance

Set `OMS_DISABLE_PAPER_BUYING_POWER_ARM=1` on the execution host to block new-policy authorization and entries. Protection, reconciliation, exits and audit history remain. Legacy preview policies remain isolated; informational IBKR 2109 is no longer classified as a preview rejection.

Verification uses isolated accounts and broker doubles. A natural-breakout paper trial requires separate operator authorization. Compare order, outcome/fills, protection and reconciliation with TWS. A rejection verifies the rejection path, not a successful execution trial; no qualifying signal means the trial is incomplete. Real-money execution remains disabled.
