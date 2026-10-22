# Current operational monitoring

The workspace uses live IBKR market data and paper execution only. Open a published strategy, prepare its exact instrument and quantity, then authorize once. Preparation checks broker context, ownership, execution support, funds and protection automatically. No strategy copy or publication is required for this monitoring update.

## Current attention and retained history

Activity defaults to **Current attention**. It lists concerns affecting current preparation, authorization, owned exposure or outstanding orders/operations. An unrelated paused, flat run does not create a data dependency. **History** retains recovered and retired episodes; **All diagnostics** also includes optional display failures and broker notifications with no execution impact.

Connecting, account snapshot collection, optional chart downloads, quiet observations and scheduled closures are normal progress. A clean startup has no actionable historical feed incidents. Current paper-context, watchdog and execution requirements still apply. An uncertain submission, unknown ownership, missing protection, account mismatch or active emergency stop is not cleared by restarting.

Recovery is evidence-based. There is no universal 30-second recovery observation interval and routine recovery requires no acknowledgment. Conclusively resolved order/protection concerns clear automatically after positive order, execution, ownership and protection evidence passes. An order absent from one snapshot is never assumed cancelled. Unknown execution faults remain restricted when their impact is unproven; diagnostics and investigation are retained. Legacy recovery APIs remain available for compatibility and rollback.

Emergency-stop release remains explicit. Recovery cannot arm a run or restore revoked startup authorization. Existing explicitly approved resumption permissions retain their original scope.

## Account snapshots without reconnect loops

The adapter maintains one `reqPositions` subscription for the supported single paper account. The initial `positionEnd` is required even when empty. Later snapshots use that connection's completed position view and subsequent updates. Open/completed-order requests without correlation IDs are serialized; execution and account requests use the shared read-request ID allocator. Account or connection changes fence old evidence.

The initial snapshot and later updates follow [IBKR's position-subscription contract](https://interactivebrokers.github.io/tws-api/positions.html). Service messages are classified using the [IBKR error-code reference](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes), separately from correlated order outcomes.

An incomplete snapshot reports the missing completion component and blocks new risk. Correlated components retry with bounded backoff. Uncorrelated requests remain serialized until their completion marker; the application does not disconnect healthy market data to retry an ambiguous request. Genuine transport or heartbeat loss still follows connection recovery. Last verified evidence is usable only within the existing freshness window and is immediately invalidated by adverse account/order/ownership changes.

## Subscription removal

An unused subscription can be removed during unrelated account checking. A positive journal record that an order was cancelled before submission also establishes that it needs no broker completion. Previously submitted orders still require relevant reconciliation and positive terminal outcomes.

Actual dependencies block removal with structured reasons naming the run, order, quantity or operation. Removal never disarms a run, cancels orders or closes exposure implicitly. Empty/terminal exit records do not lock a feed. Preparation has a renewable 30-second lease; closing or changing the dialog releases it and delayed cancelled preparation requests cannot recreate it. This lease is request ownership, not a recovery waiting period.

Restoring an unused FX subscription restarts its timestamped streams through existing pacing. Old live observations are discarded, while completed historical candles remain available for display. The restored feed must establish its own current readiness.

## Live breakout inputs

The previous-minute long-only breakout builds its reference from complete eligible live minutes after authorization. Downloaded candles are optional display data. Failure or completion of that download cannot authorize entries or reset an established live reference. Other graphs continue to require their actual history, volume and calculation inputs.

FX signal and bid/ask source/receipt timestamps must remain within 15 seconds at dispatch; future timestamps are held only within the established clock-alignment policy. Quiet healthy feeds can retain authorization under the bound quiet-feed policy, while dispatch waits for fresh observations and a new complete eligible minute. The entry type, published comparison, one-trade limit, exact quantity, margin policy and fill-based protection remain unchanged.

## Deployment and acceptance

The incident policy migration backs up existing state before updating classification metadata and superseding obsolete queued routine notices. Journals, published hashes, bindings, positions and approvals remain intact.

Run `.\scripts\verify.ps1` before starting the updated workspace. Validate Activity, preparation and unused subscription removal in isolated browser fixtures. Broker-connected acceptance additionally requires at least five minutes of complete account reconciliation and stable timestamped AUD.USD streams, including removal/restoration of an unused subscription. A natural paper execution trial is separate: the operator releases emergency stop and gives final authorization. No signal means the execution trial is incomplete, not passed.

Rollback must first disable new entries. Keep reconciliation, existing protection, already-requested exits and audit history available. Never restore an older database over newer order or execution evidence.
