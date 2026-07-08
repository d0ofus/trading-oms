# Order-Intent Proposals

Slice 026 adds a typed model for non-executable order-intent proposals.

This slice does not add risk orchestration, approval decisions, OMS transitions, fake broker
execution, broker connectivity, IBKR transport, order submission, HTTP mutation endpoints, or live
trading.

## Purpose

An order-intent proposal represents a strategy's suggested trading intent before risk, approval,
OMS, and fake broker execution.

It is not:

- a risk pass;
- human approval;
- an OMS order;
- a broker request;
- a routable order;
- permission to execute.

## Status

Every proposal has exactly one status:

```text
proposed_non_routable
```

Any executable-looking status is rejected.

## Proposal Shape

Accepted proposals are JSON-compatible:

```json
{
  "schema_version": 1,
  "proposal_id": "intent-001",
  "status": "proposed_non_routable",
  "source_signal_reference": "journal_sequence:1",
  "symbol": "AAPL",
  "side": "buy",
  "risk_intent": "increase",
  "quantity": 10,
  "order_type": "limit",
  "reference_price": 102.0,
  "limit_price": 102.25,
  "proposed_at": "2026-07-08T13:45:05Z",
  "protective_order_plan": {
    "schema_version": 1,
    "kind": "stop_loss",
    "stop_price": 98.0
  },
  "protective_exception_reference": null,
  "journal_references": ["journal_sequence:1"]
}
```

Proposal payloads intentionally include side, quantity, and order type because they are order
intents. They intentionally exclude broker routes, account IDs, credentials, risk-decision IDs,
approval references, submit, and transmit fields.

## Protection Requirement

Risk-increasing proposals require one of:

- a protective-order plan; or
- an approved protective-exception reference.

For buy proposals, a protective stop must be below the reference price. For sell proposals, it must
be above the reference price.

## Duplicate Prevention

`OrderIntentProposalBook` prevents duplicates in two ways:

- repeating the same `proposal_id` with the same payload is idempotent;
- repeating the same `proposal_id` with a different payload is rejected;
- creating another proposal from the same `source_signal_reference` is rejected.

## Journal Requirement

Every accepted proposal is appended to the event journal with event type:

```text
order_intent.proposed
```

## Current Limitations

- Proposals are in-memory only.
- No risk decision is evaluated in this slice.
- No approval ticket is created in this slice.
- No OMS order is created in this slice.
- No fake broker request is created in this slice.
