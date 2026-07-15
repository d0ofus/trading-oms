# ExecPlan: Candidate Slice 062 concrete IBKR paper connector

## 1. Goal

Define the complete, reviewable design for one future concrete Interactive Brokers paper-only
application-protocol connector behind the existing `IbkrPaperAdapter` boundary. The design must
preserve risk, manual approval, OMS, protection, journal, emergency-stop, idempotency, stale-data,
unknown-state, reconnect, and reconciliation gates before any future broker request can occur.

Candidate Slice 062 is transport planning only. It does not implement transport, install or invoke
an SDK, contact IBKR, authenticate a session, resolve a real contract, subscribe to market data,
transmit a paper order, receive a broker callback, or collect paper-session evidence.

The proposed supported SDK for the first implementation is the native Python client from the
official **IBKR TWS API Latest 10.48** distribution, using the established asynchronous
`EClient`/`EWrapper`/reader architecture. The version selection is fixed to the official download
state reviewed on 2026-07-15; it must not silently float. Candidate 063 must revalidate and pin the
exact official artifact and digest before adding any dependency.

## 2. Non-goals

- Adding an IBKR dependency, copied SDK source, wheel, installer, import, connector class, socket
  client, callback listener, broker probe, background thread, configuration key, API endpoint, UI
  control, or database migration.
- Starting TWS or IB Gateway, accepting a TWS dialogue, changing a TWS setting, logging in, using
  credentials, selecting an account, or opening any IBKR connection.
- Contract lookup, market-data subscription, order construction, order placement, modification,
  cancellation, execution handling, position query, or reconciliation against broker truth.
- Storing or exposing credentials, account identifiers, private operator values, tokens,
  passwords, certificates, private keys, TWS logs, raw callbacks, or raw rejection text.
- External review, paper-session evidence, paper-trading history, deployment, controlled rollout,
  production operation, live-readiness promotion, live account mode, or live trading.
- Candidate Slice 063 or any later implementation, lab, evidence, deployment, or rollout slice.

## 3. Safety constraints

- Live trading remains disabled and unauthorized. No live host, port, account mode, order route, or
  fallback may exist.
- Future transport must be disabled by default and restricted to a local TWS or IB Gateway paper
  session. The only permitted ports are TWS paper `7497` and IB Gateway paper `4002`.
- A literal or resolved destination that is not loopback must be rejected before the SDK receives
  it. Public, LAN, VPN, container-bridge, wildcard, hostname alias, proxy, redirect, and remote
  destinations are prohibited. TWS/Gateway ports must never be exposed publicly.
- A paper port and `account_mode=paper` are necessary controls but are not proof of a paper
  session. No account-identifier prefix, shape, or other private value may be used to infer mode.
- Any unresolved paper-mode proof, account ambiguity, protocol error, disconnect, callback
  conflict, stale input, idempotency ambiguity, missing protection, or reconciliation discrepancy
  must block all new risk-increasing work.
- Every connection transition, request decision, risk decision, approval decision, order intent,
  OMS transition, transport attempt, acknowledgement, status, fill, rejection, cancellation,
  disconnect, reconnect, reconciliation event, protection exception, alert, and emergency event
  must be appended to the journal using sanitized typed records.
- Risk must pass before an approval ticket can be created. A current explicit human approval must
  exist before the OMS can become submission-ready. The OMS must authorize the exact immutable
  payload before transport.
- Every risk-increasing entry must have a reviewed protective-order plan. The first paper lab must
  not allow protection exceptions. Missing expected protection must produce a critical local alert,
  block new risk, and require operator reconciliation.
- No automatic retry may repeat an order request after a timeout, disconnect, or ambiguous result.
  Reconciliation must establish broker truth first.
- Emergency-stop activation blocks new connections, contract requests, market-data requests, order
  requests, modifications, and other risk-increasing work. It does not automatically flatten,
  liquidate, globally cancel, or otherwise issue a broker request.
- Credentials remain inside the manually authenticated TWS/Gateway process. The connector must not
  accept, read, persist, display, or log them.
- Account identifiers and other private values may exist only transiently in process memory when
  received from the broker API. They must not enter configuration, repository files, journals,
  logs, metrics, traces, errors, screenshots, tests, exports, alerts, review packets, or support
  bundles.
- Readiness remains `not_ready`, the decision remains `no_go`, external-review evidence remains
  `missing`, zero controlled-rollout evidence categories are verified, and all 14 unresolved
  mandatory categories remain blocking.

## 4. Current state

### Repository facts

- `IbkrPaperAdapterConfig` already rejects live mode, enabled live trading, non-local hosts, and
  ports other than `7497` and `4002`.
- `IbkrPaperAdapter` has injected `ContractLookupConnector` and
  `PaperOrderSubmissionConnector` callables, typed paper-only plans/results, callback validation,
  append-only journal records, and local deterministic tests.
- The default contract and order connectors are unavailable. The adapter has no IBKR SDK import,
  authenticated session, protocol implementation, callback listener, or broker-derived evidence.
- Submission and callback idempotency maps are in memory. They are not sufficient for restart-safe
  transport idempotency or reconciliation.
- Existing paper operator views are representative adapter/test-double data, not an authenticated
  IBKR paper session or paper history.
- The current alert dispatcher is local/no-op, local authentication is not production
  authentication, and target-environment secret/network controls are not implemented.
- Candidate Slice 061 prepared an internal deterministic review packet, but no independent reviewer
  has accepted it. External review remains missing and all 14 rollout evidence categories remain
  blocking.

### Current official IBKR facts

The following statements are facts from official IBKR sources reviewed on 2026-07-15. They are not
claims about this repository or evidence that a broker session occurred.

| Official fact | Primary source |
| --- | --- |
| The TWS API is a TCP socket protocol through TWS or IB Gateway, and IBKR maintains a Python implementation. | [TWS API documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/) |
| The official portal lists TWS API Latest 10.48, released 2026-07-07, as the current package that includes Python; Stable 10.45 does not list Python in its package contents. | [Official API download portal](https://interactivebrokers.github.io/) |
| The TWS API is available only through the official MSI or ZIP download. Public `pip`, NuGet, or other repository copies are not hosted, endorsed, supported, or connected to IBKR. | [TWS API download instructions](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#download-the-tws-api) |
| IBKR advises direct TWS API use where possible. `ib_insync` is legacy and no longer updated; `ib_async` is not endorsed. | [Non-standard packages](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#non-standard-tws-api-languages-and-packages) |
| The new Python synchronous wrapper is beta and exposes only part of the larger API. | [TWS API architecture](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#architecture) |
| Minimum supported Python is 3.11. The repository currently targets Python 3.12. | [TWS API requirements](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#requirements) |
| Default paper ports are 7497 for TWS and 4002 for IB Gateway. TWS/Gateway supports multiple API clients distinguished by client ID. | [Installing and configuring TWS](https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/) |
| Initial connection negotiates protocol version and returns accessible accounts, the next valid order ID, and connection time. `nextValidId` is commonly used as a connection-complete signal. | [TWS API connectivity](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#connectivity) |
| `managedAccounts` occurs automatically on initial connection and contains all accessible account identifiers. | [Account information](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#account-information) |
| New order IDs must be greater than prior order IDs, and the sequence persists across TWS sessions. Client ID 0 has special manual-order binding behavior. | [Order submission and management](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#order-submission) |
| `orderStatus` messages are often duplicated. A pending cancellation is not a confirmed cancellation and may still fill. | [Order status](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#order-status) |
| Open orders, completed orders, and execution requests expose different, bounded views of broker state. Current-day limitations apply to completed/execution retrieval. | [Order management](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#order-management) |
| Error callback traffic includes errors, warnings, and informational notifications. Codes 1100, 1101, 1102, and 1300 distinguish important connectivity conditions. | [Error handling](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#error-handling) |
| Market-data permissions can differ between TWS and the API. Error-free local connectivity does not establish fresh usable market data. | [Market data](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#market-data) |
| A bracket requires careful transmit-flag sequencing so the parent and protective children are released together rather than exposing an entry prematurely. | [IBKR bracket orders](https://www.interactivebrokers.com/campus/?p=195739&post_type=ibkr-api-page) |
| TWS authentication is performed manually in the TWS/Gateway user interface, and paper use requires the operator to launch a paper login. | [TWS API introduction](https://www.interactivebrokers.com/campus/trading-lessons/what-is-the-tws-api/) and [third-party paper connections](https://www.interactivebrokers.com/campus/ibkr-api-page/third-party-connections/) |

### Design recommendations and unresolved blockers

- **Recommendation:** use official TWS API Latest 10.48 Python source with the mature asynchronous
  `EClient`/`EWrapper` path. Do not use a public registry copy, third-party wrapper, or beta
  synchronous wrapper.
- **Blocker:** Candidate 063 must record the exact official artifact filename, SHA-256 digest,
  license acceptance and redistribution decision, transitive dependency inventory, Python 3.12
  compatibility, and compatible offline TWS/Gateway build. A replacement release requires an
  amended plan and renewed review rather than a silent upgrade.
- **Recommendation:** use one stable, dedicated, nonzero client ID for this connector and prohibit
  Client ID 0, master-client observation, manual-order binding, and shared-client operation.
- **Blocker:** external review must approve the client-ID and order-ID strategy because IBKR's
  multi-client semantics can create ownership and sequencing hazards.
- **Blocker:** the reviewed official callbacks do not provide an authoritative paper/live session
  flag. Port, config, and account-identifier shape are insufficient proof. Candidate 063 cannot
  enter an order-capable state until an external reviewer accepts a fail-closed paper-session
  attestation procedure.
- **Blocker:** the current process-local idempotency maps, no-op alerts, and representative market
  data are insufficient for a real paper request. Durable outbox, fresh-data provenance,
  protection, and alert/reconciliation designs must be accepted before implementation.

## 5. Proposed design

### 5.1 Connector boundary and dependency isolation

Candidate 063 would add one `OfficialTwsPaperConnector` inside the IBKR adapter package. It would
implement the existing contract-lookup and paper-submission connector contracts through a narrow
session service. Core strategy, risk, approval, OMS, workflow, position, and journal modules must
not import the IBKR SDK or broker-specific types.

The connector would translate only between validated repository models and a minimal allowlist of
SDK request/callback fields. Raw SDK objects must not cross the adapter boundary. The connector
would not expose arbitrary SDK methods, generic request dispatch, script hooks, dynamic order
types, account queries, global cancel, manual-order binding, or live-capable configuration.

Candidate 062 adds no dependency. Candidate 063 may add the approved SDK artifact only after the
artifact, license, hash, dependency, and compatibility review is complete. The official source must
be acquired outside this repository; no unreviewed public-registry package or copied SDK tree is
acceptable.

### 5.2 Default-off, localhost-only transport

Future transport begins disabled. Enabling the process-level capability would require all of the
following at one immutable build and one local host:

1. a separately approved Candidate 063 implementation;
2. the non-secret paper-transport feature gate explicitly enabled at process start;
3. `account_mode=paper` and live trading false;
4. canonical destination `127.0.0.1` for the first supported lab profile;
5. port `7497` or `4002` matching the reviewed TWS/Gateway profile;
6. emergency stop inactive;
7. an accepted runtime paper-session attestation;
8. exactly one unambiguous accessible account held only in private process memory; and
9. a completed reconciliation barrier with no unresolved discrepancy.

The future implementation must validate the destination immediately before every connection
attempt. It must reject public and non-loopback IPs, wildcard binds, hostname aliases, redirects,
proxies, and any SDK-reported port change. It must never listen on or publish a broker port. No
fallback may try a live port or another host.

### 5.3 Session lifecycle

One session manager owns the SDK client, wrapper, reader, callback thread, monotonic request
sequence, session epoch, bounded callback queue, and shutdown. Business services never call the SDK
directly and callback methods never execute OMS or trading decisions.

| Session state | Entry and permitted behavior | Fail-closed exit |
| --- | --- | --- |
| `disabled` | Default. No SDK object, thread, or socket may be created. | Explicit approved startup may enter `disconnected`. |
| `disconnected` | No broker request. Local state remains inspectable. | Approved local start may enter `connecting`. |
| `connecting` | One bounded localhost attempt. No application request. | Timeout, duplicate client ID, SDK error, or stop returns to `disconnected` and journals a sanitized result. |
| `handshaking` | Wait for protocol negotiation, connection time, `nextValidId`, and `managedAccounts`. | Missing, late, malformed, or conflicting handshake data enters `unknown_requires_reconciliation`. |
| `paper_identity_unproven` | Hold the account list privately; emit only safe cardinality/status metadata. No contract, market-data, or order request. | Accepted attestation and one account enter `reconciling`; ambiguity or failed proof stays blocked. |
| `reconciling` | Read-only reconciliation requests only. New risk is blocked. | Exact reconciliation enters `ready_paper`; timeout or discrepancy enters `unknown_requires_reconciliation`. |
| `ready_paper` | Only allowlisted requests whose complete gates pass immediately before dispatch. | Any stale input, error, disconnect, overflow, or discrepancy leaves readiness immediately. |
| `degraded` | Informational service loss or stale market-data state. No risk-increasing request. | Recovery still requires reconciliation; otherwise enter unknown. |
| `unknown_requires_reconciliation` | No new risk, no automatic retry, and no state inference. | Only a complete reviewed reconciliation may release the block. |
| `stopping` | Reject new work, drain bounded local records, disconnect once, join the thread, and clear private memory. | Any shutdown ambiguity is journaled and remains reconciliation-required on restart. |

Each start receives a new non-secret session epoch. Deadlines, queue capacity, retry count, and
backoff are explicit and injectable for deterministic tests. Callback-queue overflow is a safety
event that immediately invalidates session readiness; callbacks must never be silently dropped.

### 5.4 Paper-mode proof and private values

Official documentation requires the operator to authenticate in TWS/Gateway and select a paper
login. The application therefore does not receive credentials and must not attempt automated
authentication.

The Candidate 063 private-value injection rule permits no generic secret/config/CLI/API surface.
Authentication values remain inside the manually operated TWS/Gateway process, and the
`managedAccounts` callback is the only planned source of a private broker value. If a later profile
requires any other private input, it must use a separately approved narrow provider that obtains the
value outside the repository, returns it once into a non-serializable memory-only context, exposes
no readback/display method, and clears it on expiry or disconnect. Until that provider and its
target-environment secret controls receive external review, the capability remains blocked.

The proposed proof is a conjunction, not any single heuristic:

- reviewed paper-only process configuration and one allowed paper port;
- operator confirmation, through the existing privileged local control boundary, that the visible
  TWS/Gateway session was deliberately logged into paper mode;
- a session-bound nonce and timestamp so an attestation cannot carry into a restart;
- exactly one accessible account reported during that same handshake; and
- successful read-only reconciliation for the same session epoch.

The attestation record contains actor, time, session epoch, and paper-only assertion, but no
credential or account identifier. It expires on disconnect, port change, process restart, operator
change, or configured deadline. Candidate 063 must not implement this recommendation until
architecture, trading-safety, and security reviewers agree that it is sufficient. If they do not,
paper identity remains unproven and transport remains blocked.

`managedAccounts` values are private. The first supported profile accepts exactly one accessible
account. Zero or multiple values, duplicate/invalid values, callback conflicts, or a later account
set change make the state unknown and block all new risk. No prefix or value pattern may select or
classify an account.

The one selected value may be retained only in a dedicated in-memory private session context for
the minimum lifetime needed to address broker requests. It must never be copied into domain models,
configuration, persistence, journal payloads, logs, metrics, traces, errors, screenshots, tests,
exports, alerts, or review packets. The context is cleared on every terminal session transition.
Future multi-account selection is out of scope and requires a separately reviewed private-value
injection mechanism.

Callback sanitization occurs before queueing. Account fields, raw rejection text, advanced reject
payloads, and other unneeded private fields are discarded at the boundary. Safe records may report
only classifications such as `account_count=one` and `paper_identity=unproven`.

### 5.5 Contract resolution

The first connector supports stock contracts only. A request originates from an already validated
`IbkrPaperContractLookupRequest`, receives a unique local request ID, and carries only the minimum
symbol, security type, currency, exchange, and primary-exchange fields approved by the existing
adapter.

The connector accumulates `contractDetails` records only until the matching
`contractDetailsEnd`. It then:

- returns `not_found` for zero exact supported matches;
- returns `ambiguous` for more than one exact supported match;
- returns `unsupported_instrument` for any non-stock or disallowed contract;
- returns a sanitized resolved contract only for exactly one match whose requested identity,
  trading class, primary exchange, currency, minimum tick, and broker contract identifier validate;
  and
- returns unknown/reconciliation-required on timeout, request-ID conflict, unexpected callback,
  disconnect, callback after completion, or raw-field validation failure.

Only the allowlisted sanitized contract identity and provenance may leave the connector. The full
SDK object and private fields are discarded. Resolution has a short explicit TTL and session epoch.
A stale or prior-session resolution cannot be used for an order. The final request must use the
exact reviewed broker contract identity; no fuzzy fallback, symbol-only substitution, or automatic
exchange change is allowed.

### 5.6 Atomic pre-transport gate

Immediately before any future paper submission, one transactionally consistent gate must prove:

- transport is enabled for the reviewed build and remains localhost paper-only;
- paper-session proof is current and the account selection is still unambiguous;
- reconciliation is complete and broker state is known;
- emergency stop is inactive;
- the market-data observation and contract resolution are fresh, same-session, and provenance-safe;
- the exact order intent passed the current risk policy;
- an explicit unexpired manual approval covers the exact immutable payload hash;
- the OMS is in the exact submission-ready state for that client order ID;
- quantity, side, order type, price, time in force, regular-hours policy, and contract are on the
  reviewed allowlist;
- duplicate and outbox checks establish that no equal or conflicting request was dispatched;
- the complete protective parent/child plan is valid; and
- a journal pre-dispatch record is durably appended.

Any mismatch blocks before the SDK call and journals a sanitized reason. Candidate 063 must not
create a bypass, lower-level public method, generic SDK escape hatch, retry helper, or direct test
route around this gate.

### 5.7 Durable idempotency, client ID, and order reference

The current in-memory maps are insufficient for transport. Candidate 063 requires a durable
append-only outbox reservation before calling the SDK. One `client_order_id` maps to one canonical
payload hash, protection-plan hash, session epoch, reserved broker order-ID set, and deterministic
opaque order reference.

The order reference is a versioned, bounded, ASCII-safe digest of repository-local immutable IDs.
It contains no account identifier, credential, symbol, operator name, strategy prose, or private
value. Collision behavior must be tested and must fail closed. IBKR documents `OrderRef` as a
user-defined value retained for an order's lifetime, so it is the primary reconciliation
correlation together with broker IDs and the local outbox record.

The order-ID allocator uses a dedicated stable nonzero client ID. It reserves a contiguous set for
the parent and protective children from the maximum of:

- the broker's current `nextValidId`;
- the durable local high-water mark; and
- every broker order ID observed during reconciliation plus one.

Reservation and outbox persistence happen atomically before dispatch. Reusing an ID for a new
payload, sharing the client ID, using Client ID 0, binding manual TWS orders, resetting the TWS
sequence, or accepting an ID regression is prohibited. An ambiguous dispatch result leaves the
outbox in `unknown_requires_reconciliation`; it is never submitted again merely because no
acknowledgement arrived.

### 5.8 Callback, order, fill, reject, and cancel reduction

SDK callbacks are translated to immutable sanitized transport events on a bounded queue. Each event
records callback type, session epoch, monotonic receive sequence, broker time when safe, local
receive time, safe correlation IDs, canonical payload digest, and journal reference. The event is
durably appended before the single-threaded reducer updates read state.

The reducer uses these sources together:

- `openOrder`/`openOrderEnd` for known open-order shape and ownership;
- `orderStatus` for status observations, accepting exact duplicates idempotently;
- `execDetails`/`execDetailsEnd` as authoritative fill observations keyed by execution identity;
- `commissionReport` as a late-associated cost observation, never as fill authority;
- `completedOrder`/`completedOrdersEnd` for current-day terminal-order reconciliation;
- structured numeric `error` codes for rejects and connectivity classification; and
- connection-close and handshake callbacks for session state.

Raw message text is untrusted and cannot drive a safety decision. It is redacted or discarded.
Unknown numeric codes, malformed callback data, correlation mismatches, cumulative-fill
regressions, duplicate IDs with conflicting content, impossible OMS transitions, and callbacks from
another client/session all enter reconciliation-required state.

A status acknowledgement does not prove a fill. A fill is reduced from execution details and may
arrive before, after, or without the expected status message. Exact duplicate executions are
ignored after journaling their duplicate classification; conflicting duplicates block. Fill
quantity can only increase and cannot exceed the approved quantity.

| Broker status class | Reduction rule |
| --- | --- |
| `ApiPending`, `PendingSubmit`, `PreSubmitted`, `Submitted` | Nonterminal observation only. Preserve working risk and expected protection; never infer a fill. |
| `Filled` | Candidate terminal observation only. Completion requires matching execution cumulative quantity, OMS state, position, and protection reconciliation. |
| `PendingCancel` | Still working and fill-capable. Continue processing executions and protection. |
| `PreCancelled`, `ApiCancelled`, `Cancelled` | Candidate cancel terminal only after executions, open/completed orders, OMS quantity, and protection agree. |
| `Inactive` | Ambiguous without correlated order/error context; do not infer rejection or cancellation. Reconcile. |
| Any unknown or contradictory value | Journal safe classification, enter unknown state, block risk, and reconcile. |

A structured order rejection may advance the OMS reject path only after order ownership,
correlation, no active/open order, no execution, and quantity state agree. Otherwise it is an
ambiguous broker outcome and remains reconciliation-required.

Cancellation is an explicit journaled OMS action addressed only to an order owned by the dedicated
client. It never uses global cancel. `PendingCancel` remains working risk: fills continue to be
accepted and protection remains required until a terminal broker state and reconciliation agree.
Timeout, disconnect, or missing cancellation confirmation stays unknown; the application does not
repeat cancellation blindly or report success.

### 5.9 Disconnect, reconnect, and reconciliation

Socket loss, callback-thread failure, queue overflow, duplicate client-ID failure, code 1100,
code 1300, or an unexpected port-change notice immediately enters
`unknown_requires_reconciliation`. Code 1101 requires market-data resubscription and full
reconciliation. Code 1102 says data was maintained, but this design still requires order,
execution, position, and outbox reconciliation before risk can resume. Informational farm-status
codes do not prove a ready session.

Reconnect uses bounded deterministic backoff and a new session epoch. It never automatically
replays contract, market-data, place, modify, or cancel requests. IBKR documents a TWS setting that
can maintain/resubmit orders after connectivity is restored; the first lab profile must keep that
behavior disabled unless external review explicitly accepts and tests it. The connector must never
assume which setting is active.

The reconciliation barrier gathers, to the extent supported by the pinned SDK:

- open API orders owned by the dedicated client;
- current-day completed API orders;
- current-day executions since the durable checkpoint;
- positions for the one private in-memory account; and
- the next valid order ID and safe session metadata.

It compares those observations with durable outbox records, OMS state, fills, positions,
protection expectations, and journal history. Broker-only orders, local-only submitted orders,
quantity/price/contract/reference mismatches, missing executions, unknown protection, order-ID
regression, account-set change, gaps across the broker's retrieval window, or a checkpoint spanning
an unprovable period all remain blocking and raise a critical alert.

Only an exact reconciliation result, journaled with safe counts/digests and acknowledged through an
authorized local operator workflow, may clear the barrier. No account identifier or raw broker
payload becomes evidence. Reconciliation completion does not promote controlled-rollout readiness.

### 5.10 Protection, partial fills, and emergency behavior

The first order-capable profile supports one reviewed stock limit-entry bracket pattern only. The
entry and all protective children are reserved and validated as one plan. Parent and earlier child
orders remain untransmitted until the final protective child releases the complete bracket using
the pinned and tested transmit sequence. Any interruption before complete release enters unknown
state and reconciliation; an untransmitted TWS-local order is not assumed durable.

The protection monitor evaluates every partial or full fill against broker-observed active
protection and approved quantity. A partial fill does not relax protection. Missing, rejected,
undersized, canceled, stale, or uncorrelated protection produces a critical alert, blocks new risk,
and requires immediate human review under a written paper-lab runbook.

The connector does not auto-flatten, auto-liquidate, global-cancel, or improvise a replacement
order because those actions can add risk. A separately approved operator may take a reviewed
risk-reducing paper action through the same OMS, journal, ownership, and reconciliation gates.
Emergency stop blocks new risk but does not suppress incoming fills or protection monitoring.

### 5.11 Failure matrix

| Failure | Required behavior |
| --- | --- |
| Stale market data or stale contract | Block before dispatch; journal; require fresh same-session input. |
| Exact duplicate callback | Journal duplicate classification; do not apply state twice. |
| Conflicting duplicate | Enter unknown state; critical alert; reconcile. |
| Out-of-order callback | Buffer only within a small deterministic window when correlation is complete; otherwise block and reconcile. |
| Disconnect before dispatch | No SDK call; release no order reservation as reusable; reconnect and reconcile. |
| Disconnect during/after dispatch | Mark outcome unknown; never auto-resubmit; reconcile by reference and broker IDs. |
| Reject | Sanitize numeric classification; transition OMS through its valid reject path; verify no fill/protection discrepancy. |
| Cancel pending | Continue fill and protection processing; do not claim canceled. |
| Unknown broker state | Block every risk-increasing action until exact reconciliation. |
| Partial fill | Update once from execution identity; require proportional/full reviewed protection; critical alert if absent. |
| Callback queue overflow or reducer crash | Stop readiness immediately, preserve durable input already written, and require reconciliation. |
| Account count/value change | Clear private context, block, and require a new paper attestation and reconciliation. |
| Emergency stop activates | Block new requests; keep receiving and journaling broker events; require operator-directed recovery. |

### 5.12 Bounded future paper-lab acceptance criteria

No paper lab occurs in Candidate 062 or automatically in Candidate 063. A later separately approved
lab may begin only when all Candidate 063 entry criteria and the applicable Candidate 064 gate are
satisfied. Its reviewed runbook must bind one immutable build, exact SDK/TWS/Gateway versions and
hashes, one local machine, one manually authenticated paper session, named operators/reviewers, a
fixed start/end window, and fail-closed abort criteria.

The first lab profile must:

- use one unambiguous paper account held privately in memory and one dedicated nonzero client ID;
- use localhost only, one allowed paper port, and documented firewall/public-exposure checks;
- allow stocks only, regular trading hours only, `DAY` limit orders only, and the smallest
  reviewer-approved quantity/notional;
- prohibit market orders, short sales, derivatives, foreign exchange, extended-hours orders,
  good-till-canceled orders, dynamic algorithms, manual-order binding, and protection exceptions;
- permit at most one active entry plan and one complete reviewed protective bracket;
- require current risk, separate manual approval, OMS, outbox, journal, fresh-data, emergency-stop,
  and reconciliation gates for the exact request;
- stop on any stale data, duplicate conflict, rejection ambiguity, disconnect, missing callback,
  unknown state, missing protection, account ambiguity, or evidence-sanitization failure; and
- end with zero unexplained orders/positions, a complete reconciliation, and a sanitized immutable
  evidence manifest that contains no credentials, account identifiers, private values, raw logs,
  or screenshots.

Acceptance requires observed and reviewed connection lifecycle, paper-mode proof, exact contract
resolution, idempotent acknowledgement/status/fill/cancel reduction, protection behavior,
disconnect/reconnect blocking, reconciliation, and journal continuity. A pass establishes only the
bounded paper-lab claim for that build/environment. It does not verify all 14 rollout categories,
authorize production-like paper operation, promote readiness, or authorize live trading.

### 5.13 External design-review checklist

Candidate 062 does not perform external review. Before Candidate 063, independent reviewers must
record scope, exact plan revision, reviewer identity/role, date, findings, severity, disposition,
and accepted residual risk. Any open P0 or P1 finding blocks entry.

**Architecture reviewer**

- Confirm official SDK identity, version/hash pinning, license handling, dependency provenance,
  Python compatibility, and TWS/Gateway compatibility.
- Confirm the SDK is isolated inside the adapter and no broker type or generic method escapes.
- Confirm single ownership of client/wrapper/reader/thread, bounded queues, deterministic shutdown,
  backpressure, and callback-to-reducer separation.
- Confirm durable outbox, order-ID allocator, callback ledger, checkpoints, and restart behavior.
- Confirm no HTTP/UI/CLI method can bypass the atomic pre-transport gate.
- Confirm reconciliation covers known official retrieval limits and leaves unprovable gaps blocked.

**Trading-safety reviewer**

- Confirm paper-mode proof and account ambiguity fail closed without value-shape inference.
- Confirm dedicated client ownership, order-ID monotonicity, opaque order reference, and no blind
  retry after ambiguity.
- Confirm risk, manual approval, OMS, market freshness, contract freshness, protection, journal,
  reconciliation, and emergency-stop prerequisites bind the exact payload.
- Confirm the callback/OMS matrix for acknowledgement, status, fill, reject, cancel, partial fill,
  duplicate, conflict, and out-of-order events.
- Confirm bracket construction/transmit sequencing and missing-protection critical response.
- Confirm disconnect codes, TWS resubmission setting, daily reset, and multi-client hazards are
  explicitly tested.
- Confirm the bounded lab limits and operator runbook cannot silently expand.

**Security reviewer**

- Confirm loopback canonicalization, permitted ports, no listener/public exposure, firewall check,
  and no live/remote fallback.
- Confirm manual TWS authentication and absence of credentials from the application.
- Confirm account identifiers/raw callbacks are transient, minimized, cleared, and excluded from
  configuration, persistence, logs, metrics, traces, errors, screenshots, exports, alerts, tests,
  and packets.
- Confirm raw error/reject/TWS logs are treated as sensitive and never exported automatically.
- Confirm dependency acquisition avoids unsupported public packages and has hash/license/SBOM
  controls.
- Confirm local operator authorization, attestation expiry, audit integrity, least privilege, and
  denial behavior.
- Confirm no live port, live account mode, live capability, secret, account field, or unsafe support
  diagnostic is introduced.

## 6. Data model changes

Candidate Slice 062 changes no runtime model, schema, persistence, configuration, or journal event.

Candidate 063 may propose, in its own approved ExecPlan and migration, typed versions of:

- paper session state and safe attestation metadata without account values;
- durable transport outbox and immutable canonical payload hashes;
- dedicated client/order-ID high-water state;
- sanitized callback and execution deduplication ledger;
- reconciliation checkpoint, discrepancy, and completion records; and
- protection expectation and critical-alert linkage.

Those future models must keep private broker values out of general persistence and expose only the
minimum safe identifiers needed for deterministic idempotency and audit. This list is a design
recommendation, not an approved schema change.

## 7. API changes

None.

Candidate Slice 062 adds no HTTP route, WebSocket, CLI, UI action, connector method, config key,
credential field, account field, host field, order action, callback listener, or external
integration. Candidate 063 must not add a generic broker API. Any future operator control requires
its own typed, authorized, journaled, paper-only review and must not expose private values.

## 8. Test plan

### Candidate 062 documentation tests

- Assert this ExecPlan has all 13 required sections and identifies official TWS API Latest 10.48,
  the official download-only rule, and the classic asynchronous SDK architecture.
- Assert the plan explicitly separates official facts, repository facts, design recommendations,
  and unresolved blockers.
- Assert all named safety topics, external-review areas, bounded-lab limits, and Candidate 063 entry
  criteria exist.
- Assert readiness is `not_ready`, external review is `missing`, and all 14 categories remain
  blocking.
- Assert dependency files contain no IBKR SDK or third-party wrapper dependency.
- Assert the branch adds no backend/frontend implementation, socket, API, config, credential,
  account, connector, or runtime file.

### Candidate 063 deterministic implementation tests required before contact

- Unit-test destination canonicalization, paper ports, default-off state, state transitions,
  deadlines, queue overflow, shutdown, and private-value sanitization with no socket.
- Wrap the SDK behind a narrow testable port and drive deterministic fake wrapper callbacks; do not
  contact TWS/Gateway or IBKR in CI.
- Test missing/late/conflicting handshake events, paper-attestation expiry, zero/multiple accounts,
  account-set changes, and private-memory clearing.
- Test exact/zero/multiple contract matches, request-ID collision, end marker, timeout, stale TTL,
  callback-after-end, and disconnect.
- Test durable outbox crash points before dispatch, during ambiguous dispatch, after callback, and
  during journal/reducer update.
- Test monotonic order-ID allocation against next-valid, durable high-water, observed open orders,
  restart, regression, concurrent reservation, and collision.
- Test stable opaque order-reference generation, length/charset, collision rejection, and absence of
  private input.
- Test every gate independently and in combination, including stale market data, expired approval,
  changed payload, wrong OMS state, active emergency stop, missing protection, and reconciliation
  required.
- Parameterize duplicated, conflicting, stale, out-of-order, wrong-session, wrong-client, and
  malformed `openOrder`, `orderStatus`, execution, commission, completed-order, reject, and cancel
  events.
- Replay deterministic callback transcripts twice and prove identical journal/read-model results.
- Chaos-test disconnect before/during/after dispatch, codes 1100/1101/1102/1300, reader failure,
  queue overflow, restart across a callback, daily reset window, and TWS resubmission-setting
  assumptions.
- Test partial/full fills, late cancel fills, protection-child reject/cancel/mismatch, and critical
  missing-protection alerts without auto-flatten or global cancel.
- Test reconciliation with exact match, broker-only order, local-only order, missing execution,
  position mismatch, order-reference mismatch, retrieval-window gap, and account change.
- Scan source, configuration, fixtures, snapshots, logs, errors, and generated evidence for secrets,
  account identifiers, public hosts, live ports, live-mode fields, and unsupported SDK claims.
- Run all existing unit, integration, replay, frontend, security, and resilience checks.

### Future bounded lab tests

The paper lab uses a separately approved runbook and immutable build. It must validate observed
session, request, callback, protection, disconnect, reconciliation, and evidence behavior without
putting credentials, account identifiers, raw logs, or screenshots in the repository. Its results
remain external evidence pending independent acceptance and do not modify readiness automatically.

## 9. Verification commands

Candidate Slice 062:

```powershell
python -m pytest backend\tests\test_candidate_slice_062_execplan.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
git diff --check
git diff --name-status origin/main...HEAD
```

No Candidate 062 verification command may install/import the IBKR SDK, open a broker socket, start
TWS/Gateway, read private environment values, or contact IBKR.

## 10. Rollback plan

Revert the single Candidate Slice 062 documentation/test commit. Rollback removes only this
planning artifact, its documentation tests, and documentation references.

There is no SDK, transport, socket, thread, endpoint, config key, schema, broker session, private
value, order, callback, deployment, or external state to undo. Readiness remains `not_ready` before,
during, and after rollback. If any implementation or broker interaction is discovered, rollback is
not sufficient: stop work, activate the local emergency posture where applicable, preserve the
journal, inspect for private-value leakage, and require human incident review.

## 11. Implementation steps

1. Add this Candidate 062 ExecPlan as the first file change.
2. Add failing-first documentation tests for required content, plan-only scope, official SDK
   selection, dependency absence, and fail-closed readiness posture.
3. Update `docs/SLICES.md`, `docs/SECURITY_BASELINE.md`, and README discoverability without changing
   runtime behavior.
4. Run the focused documentation test and fix documentation/test failures only.
5. Run the full repository verifier and `git diff --check`.
6. Self-review every changed line for secret leakage, public network exposure, unsupported SDK
   claims, live-order affordances, readiness promotion, safety-gate bypass, and scope creep.
7. Fix all P0/P1 findings, commit and push the dedicated Candidate 062 branch, and create a PR if
   authentication permits.
8. Stop. Do not begin Candidate 063, contact IBKR, authenticate, or run a paper lab.

## 12. Completion criteria

- This ExecPlan exists and is the first Candidate 062 file edit.
- The selected SDK is explicit: official native Python TWS API Latest 10.48, classic asynchronous
  client/wrapper architecture, exact artifact revalidation required, no public registry or
  third-party wrapper.
- Official facts, repository facts, recommendations, and unresolved blockers are visibly distinct
  and linked to current official sources.
- The connector boundary, default-off local transport, paper ports, public-network rejection,
  session lifecycle, paper proof, private values, account ambiguity, contract resolution, atomic
  safety gates, durable idempotency, callbacks, cancels, reconnect, reconciliation, stale/duplicate/
  out-of-order/unknown/partial-fill behavior, protection, tests, bounded lab, external review,
  rollback, and Candidate 063 gate are fully specified.
- Documentation tests enforce the planning-only boundary and no IBKR dependency is present.
- Focused and full verification pass.
- No SDK, implementation, socket call, endpoint, credential/account/config field, broker probe,
  paper session, real request, callback listener, deployment, rollout, production operation, or
  live capability is added.
- Candidate Slice 062 does not claim external review, paper-session evidence, paper-trading history,
  production readiness, or rollout approval.
- Readiness remains `not_ready`; external-review evidence remains `missing`; zero categories are
  verified; all 14 unresolved mandatory evidence categories remain blocking.
- Work stops before Candidate 063.

### Explicit Candidate 063 entry criteria

Candidate 063 is blocked until every item below has durable human-review evidence:

- Candidate 062 is reviewed, approved, merged, and unchanged for the implementation baseline.
- A separate explicit human approval authorizes Candidate 063 implementation only; it does not
  authorize IBKR contact or a paper lab.
- Independent architecture, trading-safety, and security reviewers have assessed this exact plan;
  all P0/P1 findings are resolved and accepted residual risks are recorded.
- The official TWS API 10.48 Python artifact filename, source URL, SHA-256, license handling,
  transitive dependencies, Python 3.12 compatibility, and compatible offline TWS/Gateway version
  are pinned. If 10.48 is unavailable or superseded, this plan is amended and re-reviewed.
- The paper-session attestation procedure is accepted as sufficient; otherwise order-capable state
  remains impossible.
- The dedicated nonzero client ID, order-ID allocator, opaque order reference, durable outbox,
  crash recovery, callback ledger, and reconciliation design are accepted.
- Exactly-one-account support and private in-memory handling are accepted; multi-account operation
  remains unsupported.
- Fresh market-data provenance, contract TTL, bracket/transmit behavior, protection monitoring,
  no-op-alert limitation, emergency response, and operator runbook are resolved.
- Local-only destination enforcement and no-public-exposure evidence procedure are accepted.
- Deterministic unit/integration/replay/chaos tests and secret/account leakage scans are approved and
  require no real broker contact in CI.
- Candidate 064 or another separately approved bounded-lab gate is required before contacting,
  authenticating with, or sending a request to IBKR.
- Readiness remains `not_ready`, external review of operational evidence remains `missing`, and all
  unresolved controlled-rollout items remain blocking.

## 13. Risks and assumptions

- Official API versions and packaging change. This plan relies on the 2026-07-15 portal state;
  version drift requires an explicit plan amendment, not an automatic upgrade.
- TWS API 10.48 is a proposed dependency, not an installed or tested one. Documentation review does
  not prove runtime compatibility with this repository.
- The official non-commercial license restricts use and redistribution. Legal/license review is a
  Candidate 063 blocker, not a box satisfied by linking the download page.
- IBKR's paper environment differs from live behavior and may simulate fills/order types. Paper
  success must never be extrapolated to live readiness.
- Port and operator attestation may not be sufficient paper-mode proof. Until independent reviewers
  accept an authoritative procedure, the connector must remain unable to submit.
- Exactly-one-account support deliberately rejects valid multi-account users rather than risk an
  ambiguous selection. Expansion requires a new private-value design and approval.
- Broker retrieval windows can leave gaps after long outages or a day boundary. An unprovable gap
  remains unknown and requires human resolution; the system must not infer a clean state.
- The current in-memory adapter idempotency and local/no-op alerting are inadequate for broker
  transport. Candidate 063 must not reuse them as if they were production controls.
- Callback order and completeness are not guaranteed by local expectations. Durable correlation,
  duplicate handling, and reconciliation are mandatory even when tests appear orderly.
- TWS settings, including read-only mode and maintain/resubmit behavior, are operator-controlled and
  can change outside the application. Configuration evidence and drift handling require external
  review.
- Protective bracket sequencing reduces but does not eliminate exposure during failures. Missing
  or ambiguous protection always requires a critical response and blocks new risk.
- Candidate 062 planning does not constitute independent review, operational evidence, an
  authenticated paper session, paper-order evidence, deployment readiness, rollout approval, or
  live-trading authorization.
