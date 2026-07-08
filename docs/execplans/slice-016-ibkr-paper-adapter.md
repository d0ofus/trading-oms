# ExecPlan: Slice 016 IBKR Paper Adapter

## 1. Goal

Add the first IBKR paper adapter foundation behind a broker-specific adapter boundary while keeping
the repository free of live trading, real credentials, network transport, and order-submission
paths.

## 2. Non-goals

- Live trading.
- Live IBKR account mode.
- Real broker credentials, account IDs, certificates, private keys, passwords, tokens, or secrets.
- Public IBKR host or port exposure.
- IBKR SDK dependency.
- Socket or network transport.
- Connecting to TWS or IB Gateway.
- Submitting, placing, transmitting, cancelling, or modifying real or paper broker orders.
- Market-data subscriptions.
- Contract resolution against IBKR.
- OMS orchestration.
- Approval workflow orchestration.
- Reconnect/reconciliation/chaos behavior beyond explicit local state representation.
- UI changes.

## 3. Safety constraints

- Do not enable live trading.
- Do not add any code path that can transmit a live order.
- Do not add credentials, account IDs, passwords, certificates, private keys, tokens, or secrets.
- IBKR adapter settings must be paper-only.
- IBKR host settings must remain localhost-only.
- IBKR ports must be limited to known local paper TWS/Gateway ports.
- Unknown IBKR state must be explicit and must block local order-plan creation.
- Adapter events must be journaled.
- Core OMS and risk modules must not import IBKR-specific code.

## 4. Current state

The backend already has:

- safety-first `Settings` with live trading disabled, localhost-only IBKR host validation, and
  paper-only IBKR account mode;
- a simulation-only `FakeBroker` with validated `BrokerOrderRequest` records;
- event journaling for critical domain events;
- OMS and risk modules that remain broker-agnostic.

`docs/IBKR_ADAPTER_DESIGN.md` exists but says the adapter is not implemented.

## 5. Proposed design

Add `trading_oms_backend.ibkr_paper_adapter` with:

- `IbkrPaperAdapterConfig` for paper-only, localhost-only adapter configuration;
- `IbkrConnectionStateRecord` for local connection-state records;
- `IbkrPaperOrderPlan` for non-transmitting local paper order plans derived from validated
  `BrokerOrderRequest` instances;
- `IbkrPaperAdapter` that can journal connection-state records and local order plans.

The adapter will not import an IBKR SDK, open sockets, call network APIs, or expose submit/place/
transmit/cancel/modify methods.

## 6. Data model changes

No database tables or migrations.

New in-memory/domain records:

- `IbkrPaperAdapterConfig`
- `IbkrConnectionStateRecord`
- `IbkrPaperOrderPlan`

## 7. API changes

No HTTP API, CLI command, config key, dependency, network endpoint, or persistence change.

The new backend module exposes local Python types and methods only.

## 8. Test plan

- Unit tests for safe adapter defaults and `Settings` conversion.
- Unit tests rejecting live trading, non-paper account mode, public hosts, and non-paper ports.
- Unit tests for connection-state journaling and unknown-state reconciliation flags.
- Unit tests for local paper order-plan creation and journaling from `BrokerOrderRequest`.
- Unit tests proving unknown state blocks order-plan creation.
- Unit tests proving payloads contain no account, credential, secret, host, port, socket, submit, or
  transmit fields.
- Unit tests proving the module does not import known network or IBKR SDK modules and the adapter
  exposes no submit/place/transmit/cancel/modify methods.

## 9. Verification commands

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the slice branch changes to remove the IBKR paper adapter module, tests, docs, ExecPlan, and
Slice 016 status updates. No persistent data or external state is introduced.

## 11. Implementation steps

1. Add focused IBKR paper adapter tests.
2. Implement the local paper-only adapter module.
3. Update IBKR adapter docs, configuration docs, architecture docs, README, and slice status.
4. Run verification and repair failures.
5. Self-review and red-team the adapter boundary.

## 12. Completion criteria

- IBKR paper adapter module exists.
- Adapter config validates paper-only mode, live trading disabled, localhost-only host, and known
  paper ports.
- Adapter exposes broker-specific behavior behind an isolated adapter boundary.
- Adapter can record local paper connection state without opening network connections.
- Adapter can build and journal a local non-transmitting paper order plan from a validated
  `BrokerOrderRequest`.
- Unknown IBKR state is represented explicitly and marked as requiring reconciliation.
- Adapter rejects unsafe settings, unsafe order requests, and non-paper account mode.
- Tests cover config validation, state journaling, order-plan journaling, unsafe rejection, and no
  account/credential/live-transmission fields.
- Verification passes.
- No IBKR SDK, socket, network transport, live broker connectivity, or order submission path is
  added.
- No real credentials, account IDs, tokens, certificates, private keys, passwords, or secrets are
  introduced.

## 13. Risks and assumptions

- This slice intentionally creates a local adapter foundation, not an IBKR network client.
- A later paper-connectivity slice must explicitly design reconnect, reconciliation, duplicate
  prevention, and unknown-state handling before any paper order transport is introduced.
- Future IBKR SDK integration must remain isolated behind this adapter boundary and must preserve
  paper-only settings.
