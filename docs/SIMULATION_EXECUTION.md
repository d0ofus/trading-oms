# Simulation Execution

The local simulation execution path advances a risk-passed, manually approved order through the
explicit OMS and the simulation-only fake broker. Saved-workflow execution is now durable and
restart-recoverable; it remains a separate deliberate action after approval.

This capability does not add IBKR transport, a broker connection, account identifiers, credentials,
network order submission, external alert delivery, production rollout, or live trading.

## Saved-Workflow Endpoint

```text
POST /api/workflows/{workflow_id}/simulation-runs/{run_id}/execute
```

The strict body binds one command to the persisted workflow version, run, approval ticket,
committed approval decision, order intent, risk decision, OMS order, execution ID, operator,
timestamp, reference, reason, known simulated-broker-state observation, and deterministic
protection observation. The endpoint requires `administer_system`; the body actor must match the
authenticated local Admin. An Approver cannot execute, and recording approval never calls this
endpoint automatically.

## Flow

The accepted path requires a durable `approved_not_executed` run:

```text
committed approval evidence
-> durable pending execution reservation
-> OMS APPROVED
-> OMS SUBMITTED
-> local fake-broker acknowledgement
-> OMS ACKNOWLEDGED
-> deterministic local fake fill
-> OMS FILLED
-> simulated position and protection observation
-> one local alert intent and no-op dispatch
-> workflow node statuses and execution-completed event
-> durable committed execution evidence
```

The fake-broker outcome exposed by this endpoint is fixed to deterministic acknowledge-and-fill.
The generic in-memory execution domain still tests acknowledge-only, fill, cancel, and reject
outcomes, but those outcomes are not operator-selectable through the saved-workflow API or UI.

## Durability And Idempotency

SQLite schema version 4 reserves the canonical execution request before any OMS or fake-broker
side effect. Finalization stores the typed execution record, updated run record, and digest-bound
expanded journal manifest.

An exact committed retry, including after backend restart, returns the original record without
another order, transition, fill, position, alert, node-status event, or journal append. Conflicting
requests fail. A dedicated non-blocking gate rejects simultaneous execution requests. A `pending`, partial,
malformed, digest-invalid, source-mismatched, or contradictory row is unavailable and is never
automatically rerun, repaired, or presented as successful.

The execution context is reconstructed from strict persisted evidence. Its original saved workflow
version remains authoritative even if the editable workflow definition is later updated.

## Protection And Alerts

A protective-order plan must already be present in the accepted proposal and passed risk evidence.
`expected_protection_present` is a deterministic simulation observation, not a broker claim.

- `true` records a protected simulated position and one informational local alert.
- `false` records `executed_protection_missing`, one critical local alert, local no-op dispatch,
  and `risk_increasing_actions_blocked=true`.

No protective order is sent anywhere. Alert delivery is always local/no-op.

## Fail-Closed Rules

Execution is blocked for an unapproved or rejected run, an expired approval, a stale or mismatched
version, any ticket/decision/intent/risk/order attribution mismatch, missing protection plan,
unknown simulated broker state, active emergency stop, actor or role mismatch, prior conflicting
execution, interrupted persistence, malformed evidence, digest failure, or contradictory source
journal evidence.

Trusted blocked attempts append an attributable `workflow_simulation.execution_blocked` event.
Emergency-stop blocks use the emergency-stop audit event. Invalid or corrupt durable evidence
remains preserved for investigation and returns a generic unavailable response.

## Operator UI

An eligible selected run shows a `SIMULATION ONLY` execution panel. It displays the exact workflow
version, run, approval, order intent, risk decision, OMS order, and protection facts. Admin must
first review the command and then check a second confirmation before execution is enabled. The UI
shows executing, completed, protection-blocked, conflict, unavailable, and recovered states and
reloads the run inspector from backend evidence after success.

After commit, the broader read-only operations surfaces project the same validated execution into
orders, positions, alerts, protection monitoring, and audit events. Every projected record carries
exact workflow/version/run/execution lineage and is explicitly local-only, simulated,
fake-broker-derived, and externally unverified. The projection adds no execution action.

There are no broker, account, credential, host, port, live-order, production-rollout, or external-
alert controls.

## Remaining Boundary

This is bounded local simulation evidence. Candidate 063, every IBKR SDK/socket/transport action,
paper-session operation, deployment, production rollout, and live trading remain deferred behind
their existing separate approval and review gates.
