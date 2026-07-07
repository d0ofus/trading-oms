# Approval Tickets

Slice 011 introduces deterministic, local approval tickets for semi-automatic human approval.

It does not add live broker integration, IBKR connectivity, network access, real broker
credentials, automatic execution after approval, UI approval screens, alert delivery, Telegram
integration, database migrations, position tracking, OMS orchestration, fake broker orchestration,
or live trading.

## Purpose

Approval tickets are the human gate between passed risk decisions and any future execution
workflow.

The approval ticket component is local and in-memory. It can:

- create pending tickets from passed risk-decision context and OMS pending-approval context;
- apply explicit approve, reject, expire, and cancel decisions;
- enforce idempotency for ticket creation and decisions;
- append every newly accepted ticket creation and decision to the event journal.

Approved tickets are approval records only. They do not submit orders, call brokers, advance OMS
state, or emit execution instructions.

## Ticket Creation

Tickets can be created only when:

- `risk_decision_result` is `passed`;
- `oms_state` is `PENDING_APPROVAL`;
- order identifiers, symbol, side, quantity, risk intent, risk decision ID, and OMS transition
  reference are valid;
- `expires_at` is after `created_at`.

Ticket creation appends an event with type:

```text
approval.ticket.created
```

## Decisions

Decision states:

- `approved`
- `rejected`
- `expired`
- `cancelled`

Every decision requires:

- decision ID;
- ticket ID;
- decided timestamp;
- actor;
- decision reference;
- reason.

Approval, rejection, and cancellation must happen before the ticket expires. Expiry must happen at
or after the ticket expiry timestamp.

Decisions append an event with type:

```text
approval.ticket.decided
```

## Idempotency

`ticket_id` is the idempotency key for ticket creation.

`decision_id` is the idempotency key for decisions.

Replaying the same ID with the same payload returns the original record and does not append another
journal entry. Replaying the same ID with a different payload is rejected.

## Guarantees

- Approval ticket behavior is local and deterministic.
- Tickets cannot be created from blocked risk decisions.
- Tickets require OMS pending-approval context.
- Every newly accepted ticket creation and decision is journaled.
- Approved tickets do not automatically submit orders.
- Ticket creation and decision payloads contain no live broker routing, account, credential,
  network, submission, or transmission fields.
- Invalid identifiers, timestamps, states, actors, references, reasons, and expiry ordering fail
  validation.

## Current Limitations

- State is in memory only.
- No database-backed approval persistence yet.
- No authentication or authorization model yet.
- No UI approval screen yet.
- No alert delivery yet.
- No OMS state advancement after approval yet.
- No fake broker orchestration yet.
- Expiry is applied by an explicit decision request, not by a scheduler.
- Callers must not put secrets in actor, reason, reference, or request fields.
