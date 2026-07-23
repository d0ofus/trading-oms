# Saved Simulation Run Comparison

The read-only saved-run comparison candidate lets an operator compare exactly two committed local
simulation runs and prepare an audit bundle for one exact selected run and journal scope.

It does not approve, reject, execute, retry, repair, delete, rewrite, connect, transmit, deliver,
deploy, or enable live trading.

## Evidence Boundary

The backend accepts two explicit workflow/run selectors and reconstructs both runs from committed
SQLite records plus their SHA-256-bound append-only JSONL manifests. Before returning either run,
it validates every available committed projection source and the complete selected lifecycle.

The response contains these ordered sections:

1. workflow identity and expected version;
2. run state and replay identity;
3. strategy signal;
4. non-routable order intent;
5. risk decision;
6. approval ticket;
7. optional manual approval decision;
8. optional local fake-broker execution;
9. optional protection state;
10. local alert evidence;
11. journal manifest, references, record digests, and provenance.

Each section is classified as `added`, `removed`, `changed`, or `unchanged`. Field differences are
sorted by path, and the response includes a deterministic comparison SHA-256. Selecting the same
workflow/run in both slots is allowed and is the explicit identical-run state.

Missing, pending, corrupt, duplicate, mixed-source, cross-run, contradictory, or otherwise
unavailable evidence fails closed. The service never substitutes representative records, repairs
the journal, or returns a partial comparison.

## Read-Only API

```text
GET /api/simulation-run-comparison
    ?left_workflow_id=...
    &left_run_id=...
    &right_workflow_id=...
    &right_run_id=...
```

Invalid selectors return generic HTTP 400, unknown selectors return generic HTTP 404, and
unavailable durable evidence returns generic HTTP 503. No comparison mutation route exists.

## Exact Audit Selection

The existing audit-export GET endpoint supports an all-or-none selected-run mode:

```text
GET /api/audit-export-bundle
    ?workflow_id=...
    &run_id=...
    &expected_manifest_sha256=...
    &journal_scope=complete_run_manifest
```

For one exact manifest event:

```text
GET /api/audit-export-bundle
    ?workflow_id=...
    &run_id=...
    &expected_manifest_sha256=...
    &journal_scope=single_journal_event
    &journal_sequence=...
```

The returned manifest binds the selected workflow version, run, lifecycle status, complete source
manifest digest and references, selected references and record digests, journal scope, local
simulation provenance, and deterministic selection SHA-256.

`complete_run_manifest` includes every manifest record. `single_journal_event` includes only one
sequence that is already in that manifest while retaining the complete source-manifest binding.
A stale manifest digest returns generic HTTP 409. A sequence outside the selected manifest or an
incomplete query returns generic HTTP 400.

The parameterless local-review export remains available for compatibility.

## Operator UI

The `Run comparison` section provides:

- separate left and right selectors populated only from committed saved-run history;
- an explicit Compare command;
- loading, empty, unavailable, partial-unavailable, identical, and differing states;
- deterministic section counts, exact selectors, digests, journal references, and provenance;
- left/right audit target selection;
- complete-manifest or one-event journal scope;
- an explicit Prepare audit bundle command;
- a local data-URL JSON download only after strict response validation.

Changing a run selector, audit target, scope, or event invalidates the prior result. No comparison
or export request is automatic.

## Safety Guarantees

- Comparison and selected export use `GET` only.
- Durable runs never fall back to representative data.
- Every selected source is local, simulated, and externally unverified.
- Executed runs may be classified `fake_broker_derived`; `broker_derived` remains false.
- Live trading and live authorization remain false.
- No account, credential, host, port, token, secret, external alert, deployment, or rollout field
  is accepted or rendered.
- No approval, execution, cancellation, repair, retry, deletion, journal rewrite, or broker action
  is added.

## Current Limitations

- Comparison is local and uses committed saved-workflow simulations only.
- Digests provide deterministic integrity bindings, not signatures or external verification.
- Historical workflow documents are not versioned separately; the run binds its expected workflow
  version but does not claim that a newer definition is the historical document.
- JSON download stays in the browser. There is no upload, external delivery, retention workflow,
  or review transport.
