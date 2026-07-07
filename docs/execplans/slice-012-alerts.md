# ExecPlan: Slice 012 alerts

## 1. Goal

Add a local, safety-first alerting foundation that records alert intents and dispatch outcomes in
the event journal and can format Telegram-compatible alert text without adding credentials,
network delivery, or live trading behavior.

## 2. Non-goals

- Real Telegram integration.
- Telegram bot tokens, chat IDs, or account IDs.
- Network delivery.
- Broker integration.
- Order submission.
- Live trading.
- UI.
- Database migrations.
- Incident automation or escalation workflows.

## 3. Safety constraints

- Do not enable live trading.
- Do not add broker connectivity or any order-transmission path.
- Do not add real Telegram tokens, chat IDs, credentials, secrets, or account IDs.
- Alert payloads must not contain credential-shaped fields.
- Every accepted alert intent must be appended to the event journal.
- Every accepted dispatch outcome must be appended to the event journal.
- Dispatching in this slice must be local/no-op only.
- Telegram support must be formatting-only, with no token handling and no network transport.

## 4. Current state

The backend has a JSONL event journal plus deterministic domain modules for risk, fake broker,
OMS, and approval tickets. Those modules use frozen dataclasses, explicit validation, and unit
tests that prove journaling and secret/live-order boundaries. `docs/SLICES.md` contains Slice 012
as the approved alerts slice on branch `slice-012-alerts`.

## 5. Proposed design

Add `trading_oms_backend.alerts` with:

- alert intent and dispatch outcome dataclasses;
- explicit severity and channel validation;
- an `AlertBook` that records alert intents and local dispatch outcomes;
- a no-op dispatcher implementing a small dispatcher protocol;
- a Telegram-compatible formatter that returns text payload data only, with no token, chat ID,
  URL, or network transport;
- recursive payload validation that rejects credential-shaped metadata keys and obvious
  credential labels in text values.

## 6. Data model changes

Add in-memory Python dataclasses only:

- `AlertIntentRequest`
- `AlertIntent`
- `AlertDispatchRequest`
- `AlertDispatchOutcome`
- `TelegramAlertPayload`

No database tables or migrations.

## 7. API changes

No HTTP API, CLI, config, dependency, or public service endpoint changes.

The new backend module exposes local Python interfaces for future orchestration code.

## 8. Test plan

- Unit tests for creating alert intents and appending `alert.intent.created` events.
- Unit tests for no-op dispatch and appending `alert.dispatch.recorded` events.
- Unit tests for Telegram-compatible formatting with no token or chat ID fields.
- Unit tests for supported severities and channels.
- Unit tests for invalid identifiers, timestamps, payload values, metadata, and secret-shaped
  fields.
- Unit tests proving no broker routing, order submission, network, token, or secret fields appear
  in alert payloads.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the slice branch changes to remove the alerts module, tests, docs, ExecPlan, and Slice 012
status updates. No persistent schema or external state is introduced.

## 11. Implementation steps

1. Add focused alert unit tests.
2. Implement `trading_oms_backend.alerts`.
3. Add alert behavior documentation.
4. Update `docs/SLICES.md` acceptance criteria and final status.
5. Run verification and repair failures.
6. Self-review and red-team the diff.

## 12. Completion criteria

- Alert module exists.
- Alerts represent informational, warning, critical, and emergency severities explicitly.
- Alert intents and dispatch outcomes are journaled.
- Telegram-compatible formatting exists without token handling or network transport.
- Alert payloads reject credential-shaped fields.
- Tests cover creation, formatting, journaling, validation failures, and no secret/no network
  behavior.
- Verification passes.
- No live broker connectivity or order submission path is added.
- No real Telegram tokens or secrets are introduced.

## 13. Risks and assumptions

- The formatter intentionally omits Telegram `chat_id` and token handling; a future adapter must
  add those outside repository files and behind explicit safety gates.
- Secret detection is conservative and rejects metadata keys such as token, password, secret,
  credential, account, and chat identifiers.
- The no-op dispatcher records what would be dispatched but does not attempt delivery.
