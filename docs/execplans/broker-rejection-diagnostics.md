# ExecPlan: Broker rejection diagnostics and incident correlation

## 1. Goal

Explain broker rejections without exposing private broker messages. Correlate the
recorded Inactive / 201 / repeated callbacks / Cancelled sequence to one order
incident and retain the rejection cause separately from final broker status.

## 2. Non-goals

No broker settings changes, automatic rejection overrides, live trading, order
retries, risk-limit changes, incident release, or restoration of authorizations.
The unavailable explanation for the historical rejection cannot be reconstructed.

## 3. Safety constraints

Paper-only adapter guards, $25 qualification, freshness and approval checks remain.
Uncertainty blocks new risk; confirmed executions and protection remain authoritative.
Retain all historical journal evidence. Parse private rejection input only at the
adapter boundary; emit allowlisted categories and generated explanations, never raw
messages, advanced JSON, credentials, or account identifiers. No broker observation
session may place orders without a fresh operator-armed run.

## 4. Current state

The error callback discards advanced rejection JSON and routes ordinary messages
through the data classifier. The engine synthesizes Rejected for owned code 201,
then falls through to a second broker_201 incident. OMS projection differences
raise order_uncertain repeatedly. Completed Cancelled hides prior rejection.
Incident identity currently consists of code and scope, without order correlation.

## 5. Proposed design

Add a bounded rejection classifier and validate its output before persistence.
Correlate owned failures by durable intent and broker leg, preserving workspace
restriction scope and dedicated recovery policy. Add an optional indexed incident
correlation key; legacy episodes keep the empty key. Persist a semantic failure
projection transactionally with incident changes. Duplicate callbacks are audited
but do not invalidate reconciliation, increment occurrences, or reset recovery.
Refining unknown to confirmed rejection updates the same episode and invalidates
stale review evidence without counting another attempt. Contradictory outcomes
still create/reset appropriate restrictions. Released historical episodes are not
reopened by identical old callbacks after restart.

Keep broker status and execution-derived outcome separate. An entry with a retained
rejection and confirmed zero fills is described as rejected even if the last broker
status is Cancelled. Unreconciled zero-fill status is not proof of no execution.
Expose diagnostics in order details, run status and incident review. Existing legacy
episodes remain untouched and require their normal explicit recovery workflow.

## 6. Data model changes

Add incident correlation_key TEXT NOT NULL DEFAULT '' and replace only the active
identity index to include it. Back up an existing database before this additive
migration; preserve all prior payloads and journal records. Add bounded per-order
failure documents and rejection fields to broker observations and incident payloads.

## 7. API changes

Add optional rejection diagnostics and originating order context to existing order
and incident responses. Retain existing endpoints, state fields and client behavior.

## 8. Test plan

Regression tests first: exact recorded callback sequence, single incident and count,
unrelated orders, safe classifier and malformed input, duplicate/reordered callbacks,
recovery evidence stability, stale reviews, restart, terminal zero fill, partial and
late executions, retained reservations, and conservative uncorrelated errors.
Browser tests cover rejection cause, latest broker status and recovery countdown.
Migration tests compare immutable records before and after additive schema upgrade.

## 9. Verification commands

`.\.venv\Scripts\python.exe -m pytest backend/tests/test_workspace_rejections.py backend/tests/test_workspace_pending_orders.py -q`

`. .\.tmp\activate-dev.ps1; .\scripts\verify.ps1`

## 10. Rollback plan

Stop the execution owner before rolling back these source changes. Do not delete
journal/state or replay orders. Restore a backup only under a separate reconciled
recovery procedure. Older code does not understand multiple same-scope episodes;
do not run it against newly correlated state without reviewing that limitation.

## 11. Implementation steps

1. Record this plan and add failing regressions.
2. Add safe boundary diagnostics and additive incident correlation.
3. Correct OMS deduplication, engine routing and outcome presentation.
4. Extend UI and operating documentation; add browser coverage.
5. Run focused and full verification, self-review and document evidence.

## 12. Completion criteria

One rejected attempt produces one correlated incident, preserved rejection evidence,
and no automatic retry/release. Duplicate callbacks do not restart recovery. All
focused and repository verification pass, with external broker checks identified.

## 13. Risks and assumptions

Code 201 does not identify the rejection cause by itself. Unknown or ambiguous
messages stay unknown. The historical order and incidents are not rewritten. The
operator must obtain the TWS explanation and address the broker cause before an
operator-armed natural-breakout paper trial. Offline verification does not establish
PAXOS paper availability or successful execution.

Implementation is complete. There are 31 focused rejection regressions. Self-review
added checks for fresh identity after reconnect, legacy cancelled-history browsing,
protective-child rejection routing, and refinement of the paused run's outcome.
It also reproduced a rejected exit followed by Cancelled evading the existing
rejection retry guard; that guard now checks retained rejection evidence as well.
An initial browser check found an overflowing long status badge; the table now uses
a compact label and the inspector retains the complete outcome.

Final verification on 2026-09-22: `. .\.tmp\activate-dev.ps1` followed by
`.\scripts\verify.ps1` completed with `verify: ok`: 1,102 backend tests, 190 frontend
tests and 13 browser tests passed. Formatting, linting, type checking, compilation,
production build, secret scanning and dependency audits passed. The focused rejection,
pending-order and unified suites additionally passed 91 tests. The gate recorded the
current source fingerprint. Remaining warnings concern the existing Vite bundle size,
the test HTTP-client deprecation, terminal color settings and pip-audit lockfile advice;
no known dependency vulnerabilities were reported.

The operator-armed external paper trial was not performed: the missing TWS explanation
must be obtained and its cause addressed first. No IBKR orders, settings changes,
application-state migration, incident releases or authorizations were performed on
the operator's workspace during implementation. The backed-up additive migration runs
when the operator next starts the updated application. No commit or push was made.
