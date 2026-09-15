# Typed strategy simulation

The **Typed strategy builder** adds an opening-breakout template alongside the existing Visual
builder. Both remain available. Typed runs use a separate schema-v2 API, SQLite database, dataset
directory, and append-only journal. They do not replace v1 approval tickets, saved-run recovery,
execution projections, run comparison, or Candidate 062/063 readiness evidence.

## Supported behavior

The runtime accepts exactly the template's typed nodes and port connections. Node IDs, layout,
opening-range duration, and supported lifetime settings can change. Type-compatible rewiring,
additional nodes, or missing gates are rejected before save. The palette includes future building
blocks; their presence does not imply that arbitrary graphs can execute.

The template consumes immutable, ordered trade ticks for one declared contract. It selects RTH
sessions using America/New_York time, freezes the day low at the first opening-range breakout,
sizes whole shares with Decimal arithmetic, and checks the administrator risk policy. A separate
human arming action binds the workflow version/checksum, dataset, symbol, risk budget, lifetimes,
policy version, and expiry to one fingerprint. Execution requires an explicit simulation request.

The next eligible trade supplies the simulated entry price plus configured slippage. The simulator
reduces shares when necessary to keep known initial stop risk within the authorized budget and
rechecks buying power and policy limits at that price. Protective-stop and configured time exits
then inspect every remaining supplied tick, including later sessions and ticks after entry expiry.
A time exit remains due if the next supplied tick arrives the following day. An entry at or after
its configured exit time is blocked. Stop gaps can exceed the initial risk budget; that result
records a critical alert. No continuous monitoring occurs after the supplied data ends.

Historical simulation replays local data. `live_simulation` is a fake-fill simulation over an
explicitly registered forward capture; it checks freshness against server time. It does not open a
broker or market-data connection. Both modes require explicit simulated reconciliation, complete
acceptable data, an unchanged armed version, an unexpired authorization, and inactive emergency
stop. Client timestamps cannot backdate arming or execution authorization. Five-second bars,
degraded tick datasets, and typed-condition exits cannot run in this slice.

The run UI's sample scenario uses $50,000 simulated buying power, zero existing positions,
exposure and daily loss, and simulated reconciliation. These values are fixture inputs, not broker
observations. Contract identifiers and routing labels are dataset metadata only. Typed results do
not populate the existing v1 operations projections or comparison UI.

## Local operation and authorization

Start the backend and frontend using the README commands. Use one backend worker for this local
simulation slice. Journal write sessions serialize within a process; SQLite execution reservations
also reject a competing service/process reservation. This is not a multi-worker deployment design.

The existing local-development header authorization applies:

| Role | Typed capabilities |
| --- | --- |
| `viewer` | Read definitions, datasets, policy, runs and events |
| `strategy_author` | Validate, create and update typed workflows |
| `strategy_operator` | Register datasets; draft, arm, disarm and simulate runs |
| `admin` | Read and author; operate the existing emergency-stop control |

The default local identity is an administrator and cannot arm or execute typed runs. `admin` cannot
be combined with `strategy_operator` or the existing `approver` role. Local header identity is a
development facility; it remains unavailable in production. This slice adds no login system or
automatic role switching. Authorized development API clients can send `x-operator-id` and
`x-operator-roles` using the existing mechanism.

1. Save the supported template, or choose **Load saved workflow** to edit the current version.
2. Register the deterministic sample dataset using an authorized strategy operator.
3. Supply a new run ID, the saved version, dataset ID, symbol, dollar risk and future UTC expiry.
4. Create a draft, review its fingerprint and protective plan, and explicitly arm it.
5. Request fake-broker simulation and inspect the result and journal events.

Updates require the version actually loaded by the editor (`expected_version`). A stale save
returns 409; load and review the latest version before making another change. The client never
silently replaces a newer version. Editing a saved workflow disarms older drafts/arms. Run IDs and
dataset IDs are immutable; use a new run ID for a different scenario.

## API and persistence

| Paths | Operations |
| --- | --- |
| `/api/typed-workflows/catalog` | GET typed catalog |
| `/api/typed-workflows` | GET list, POST create |
| `/api/typed-workflows/{workflow_id}` | GET current, PUT update |
| `/api/typed-workflows/{workflow_id}/validate` | POST validation |
| `/api/typed-workflows/{workflow_id}/versions` | GET immutable versions |
| `/api/strategy-datasets` and `/{dataset_id}` | POST registration, GET detail |
| `/api/strategy-risk-policy` | GET immutable policy |
| `/api/typed-workflows/{workflow_id}/runs` | POST draft |
| `/api/strategy-runs/{run_id}` | GET validated state/result |
| `/api/strategy-runs/{run_id}/arm`, `/disarm`, `/simulate` | POST explicit transitions |
| `/api/strategy-runs/{run_id}/events` | GET finite SSE snapshot of that run's journal events |

Typed request bodies reject extra fields and coerced primitive types. Omitted reconciliation is
false. Set `TRADING_OMS_TYPED_STATE_DIRECTORY` to choose storage; the default is
`.tmp/typed-strategy-state` at the repository root. Keep `typed-strategy.sqlite3`,
`strategy-run-journal.jsonl`, and `datasets/` together. Existing v1 storage is unchanged. No migration
from experimental local typed state is supplied; run-evidence manifests are required for reads.

## Evidence failures and recovery

Simulation durably reserves execution before appending fill evidence. Successful reads and exact
retries validate the saved payload checksum and every referenced journal record. A completed
retry must carry the original execution inputs. A changed request is rejected without new fills.

An interrupted reservation, missing journal, or changed run evidence fails closed. Incomplete
execution blocks further typed execution in that database, including another run. API failures
return a generic 503 without filesystem or database details. There is no automatic retry, reset,
or reconstruction from partial artifacts.

Emergency activation records a persistent typed stop and disarms active drafts/arms. Clearing
does not restore prior authorizations. A typed stop survives service restart even if the existing
operations shell's separate emergency state resets; explicitly clear it through the emergency
control after reviewing the retained state. Failure during emergency handling leaves recovery
required and must not be treated as a successful reset.

Stop the local service and preserve the entire state directory before investigating an unavailable
run. Restore only a verified matching database/journal/dataset backup. Keep partial evidence for
audit. Any deliberate restart in a fresh simulation directory must be an explicit operator action;
there is no supported in-place recovery or migration command in this slice.
