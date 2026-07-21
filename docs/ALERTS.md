# Alerts

Slice 012 introduces a deterministic, local alerting foundation.

It does not add real Telegram integration, Telegram bot tokens, chat IDs, network delivery,
broker integration, order submission, UI, database migrations, incident automation, or live
trading.

## Purpose

Alerts are safety records for conditions that should be visible to humans or future notification
adapters. The current implementation is local and in-memory. It can:

- create validated alert intents;
- append every accepted alert intent to the event journal;
- record local no-op dispatch outcomes;
- append every accepted dispatch outcome to the event journal;
- format Telegram-compatible alert text without token handling, chat IDs, URLs, or network
  transport.

The no-op dispatcher records what would be dispatched. It does not send messages, make HTTP
requests, call Telegram, submit orders, or contact brokers.

## Severities

Supported severities are explicit:

- `informational`
- `warning`
- `critical`
- `emergency`

## Channels

Supported channels are:

- `local`
- `telegram`

The `telegram` channel is formatting-only in this slice. It creates a payload shape with:

- `api_method`
- `text`
- `disable_web_page_preview`

It intentionally omits `chat_id`, bot token handling, URLs, and transport configuration.

## Journal Events

Alert intent creation appends an event with type:

```text
alert.intent.created
```

No-op dispatch recording appends an event with type:

```text
alert.dispatch.recorded
```

## Validation

Alert intents validate:

- alert ID;
- source event type;
- source event reference;
- severity;
- channel;
- timestamp with timezone;
- title;
- message;
- metadata JSON payload.

Dispatch requests validate:

- dispatch ID;
- alert ID;
- dispatch timestamp with timezone;
- reason.

Metadata rejects credential-shaped field names including token, password, secret, credential,
certificate, private key, authorization, account, API key, and Telegram chat identifiers. Title,
message, reason, and metadata string values also reject obvious credential labels such as
`token=` or `password:`.

## Guarantees

- Alert behavior is local and deterministic.
- Every newly accepted alert intent is journaled.
- Every newly accepted dispatch outcome is journaled.
- Alert and dispatch IDs are idempotent for identical payloads.
- Conflicting duplicate alert or dispatch IDs are rejected.
- Telegram formatting does not include token, chat ID, URL, or network transport fields.
- Alert payloads contain no broker routing, order submission, credential, token, or secret fields.

## Current Integration And Limitations

- The standalone alert service remains in memory. Saved-workflow execution captures exactly one
  typed local alert intent and one no-op dispatch in durable execution evidence.
- A protected simulated fill creates an informational local alert; missing expected protection
  creates a critical local alert and a durable risk-increasing-actions block.
- No scheduler, escalation workflow, real Telegram adapter, webhook, or external delivery exists.
- Local authorization controls the saved-workflow execution command, not the alert domain itself.
- Callers must not put real secrets in any alert text, reference, reason, or metadata value.
