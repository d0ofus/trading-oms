# Run preparation, archival and routine recovery

The single paper workspace and prepare → review → arm workflow remain in place. Preparing, archiving or acknowledging recovery does not submit an order.

## Prepare a reusable stock run

1. In Settings resolve the exact stock. For Xiaomi use contract ID **323608988**, symbol **1810**, security type **STK**, currency **HKD**, routing exchange **SEHK**.
2. Read **Current contract search**. Acceptance starts the request; results, no matches, failures, interruption and a 30-second timeout are displayed separately. Previously resolved contracts remain separately listed. Candidate resolution preserves the entered route.
3. Use a published schema-7 stock definition. For a legacy crypto definition, open Studio → Review & publish → **Create reusable copy**. The new stock-copy draft is selected automatically. Review and publish explicitly. Ordinary Duplicate preserves the original schema and execution behavior.
4. On Trading Desk choose **Prepare a run**, select the published strategy, then the resolved contract. Studio and Testing use the same contract, sizing, protection and compatibility form.
5. Review currency, lot guidance, quantity and USD ceilings. **Prepare bound run** creates a disarmed run. Lower published ceilings, including the $25 legacy long-only budget, remain effective. If one legal lot exceeds that budget, arming/entry risk checks still block it.

Changing the selector loads the immutable published version and clears the previous form. A legacy crypto breakout selected with a stock explains the required conversion. Missing contract rules and other capability requirements still appear within the existing dialog.

## Archive inactive runs

Select the run-table checkboxes and choose **Archive selected**. One dialog shows eligibility for up to 50 runs. Confirmation archives the entire batch or rejects it with a specific reason.

Each run must be disarmed, flat and free of active reservations, unresolved orders, protective legs, cancellations and exit operations. Runs with broker order records require fresh successful reconciliation in the current verified paper session. Never-submitted runs without order records may be archived offline. Archiving does not cancel orders, close positions, unsubscribe data or release incidents.

Archived runs disappear from the default Desk list. They remain in **Run & order history → Browse records → Saved runs**, labelled Archived. They cannot be armed; prepare a new run to reuse the strategy. Unexpected late executions or conflicting broker states restore visible recovery handling. Benign duplicate history and delayed pending statuses preserve terminal-order evidence.

## Automatic routine recovery

Activity → **Routine recovery status** shows current automatic recovery and its observation countdown. Verified routine episodes release without acknowledgment. Runs still require fresh manual arming.

Eligible categories include watchdog, connectivity, contract-scoped feed/history failures and known broker services (2103, 2105, 2110). Farm identity improves correlation but is not required to classify a recognized service code. A new connection can requalify its current dependencies without a recovery message from an obsolete farm. Unknown broker messages, engine faults, order/protection/account uncertainty and emergency stop retain dedicated recovery.

Release rechecks engine identity, fresh watchdog health, verified paper context, post-failure reconciliation, applicable feeds, incident revisions and 30 continuous healthy seconds. Changed episodes or connections restart qualification. Unsubscribed feeds without run/exposure/work dependencies can retire after the same current health checks; retirement does not claim feed recovery. See [automatic recovery and stock rules](AUTOMATIC_RECOVERY_AND_STOCK_RULES.md) for the full policy.

## API and persistence

- `POST /api/runs/archive-preview` accepts `ids` (1–50 distinct run IDs).
- `POST /api/runs/archive-confirm` accepts `preview_id` and `mutation_id`.
- `POST /api/incidents/recovery-preview` and `/api/incidents/recovery-confirm` implement the routine batch review with the same confirmation shape.
- Confirmation IDs are 32 lowercase hexadecimal characters. Retrying the same mutation/preview returns its durable receipt; reusing it for different work is rejected. Operator identity comes from the authenticated session.
- `/api/market-data/resolve` retains `request` and adds a search ID, state, query and results. Authenticated `GET /api/market-data/search/{search_id}` returns status. Caches retain 20 searches and up to 200 results each. Active subscriptions and run-bound contracts survive eviction.
- Search polling permits one request in flight, waits two seconds after completion, pauses while hidden and aborts on unmount. Obsolete callbacks cannot replace a newer search.
- Routine-policy migration backs up state and journals projection changes. Historical events, published versions and approvals remain unchanged. Migration does not release restrictions.

## Verification boundary

Browser verification uses an isolated server with broker networking and stock submission disabled. Xiaomi metadata and lot evidence are synthetic fixtures, not renewed broker qualification. No production account is armed or changed by these tests.
