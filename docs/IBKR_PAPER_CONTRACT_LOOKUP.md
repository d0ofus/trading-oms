# IBKR Paper Contract Lookup

Slice 048 adds a safe paper contract lookup surface behind the existing IBKR paper adapter boundary.

The lookup validates paper-only localhost-only adapter configuration, requires a known local paper
endpoint configuration, journals lookup attempts and outcomes, and returns sanitized contract
metadata only when an adapter-bound paper lookup connector resolves a supported contract.

It is not an authenticated IBKR session, not a market-data subscription, and not evidence that an
account, order path, or paper order transport is ready.

## Scope

The lookup can:

- validate the existing paper-only adapter configuration;
- require adapter state `connected_paper` before connector use;
- reject reconciliation-required state before connector use;
- resolve supported stock contract metadata through an injected adapter-bound connector;
- reject unsupported instruments without connector use;
- reject stale resolved metadata;
- journal every lookup attempt and outcome;
- mark timeout, OS, unexpected connector, stale, or unknown outcomes as reconciliation-required.

The lookup cannot:

- authenticate;
- store account identifiers;
- use credentials, tokens, passwords, certificates, private keys, or secrets;
- import or use an IBKR SDK;
- subscribe to market data;
- request account state;
- place, submit, transmit, route, cancel, or modify orders;
- register SDK/network order status listeners;
- register SDK/network fill listeners;
- expose public IBKR ports;
- enable live trading.

## Configuration Boundary

The lookup uses `IbkrPaperAdapterConfig`, which remains:

- `account_mode: paper`;
- `live_trading_enabled: false`;
- localhost-only host values;
- known paper ports only: `7497` for TWS paper or `4002` for IB Gateway paper.

No new config keys, arbitrary host fields, account fields, credential fields, live-mode fields, API
endpoints, workflow nodes, or UI controls are added.

## Connector Boundary

`IbkrPaperAdapter.lookup_contract` accepts an injected `ContractLookupConnector` for deterministic
paper lookup behavior. This slice intentionally does not add an IBKR SDK dependency.

The connector seam keeps future SDK or protocol work inside the adapter boundary. It also allows
tests to prove validation, journaling, stale-result handling, and forbidden-surface behavior without
requiring a running TWS or IB Gateway process.

## Journal Events

Each lookup appends:

```text
ibkr.paper.contract_lookup.attempted
```

and then appends:

```text
ibkr.paper.contract_lookup.recorded
```

Lookup payloads include:

- lookup ID;
- timestamps;
- safe reason;
- endpoint kind: `tws_paper` or `gateway_paper`;
- symbol;
- security type;
- currency;
- exchange;
- status;
- reconciliation flag;
- optional failure category;
- sanitized contract metadata for successful lookups only.

Lookup payloads intentionally exclude host, port, account, credential, route, submit, transmit,
order, token, password, certificate, private key, and secret fields.

## Status Mapping

| Lookup outcome | Result status | Reconciliation |
| --- | --- | --- |
| Connector returns fresh supported stock metadata | `resolved` | `false` |
| Connector reports no matching contract | `not_found` | `false` |
| Connector reports ambiguous matches | `ambiguous` | `false` |
| Request uses an unsupported instrument type | `unsupported_instrument` | `false` |
| Adapter is disconnected | `blocked_disconnected` | `false` |
| Adapter state already requires reconciliation | `blocked_reconciliation_required` | `true` |
| Connector returns stale metadata | `stale_result_rejected` | `true` |
| Timeout, OS error, unexpected connector error, or unavailable connector | `unknown_requires_reconciliation` | `true` |

## Safety Guarantees

- Live trading remains disabled.
- No paper order transport is added.
- No order placement path is added.
- No market-data subscription path is added.
- Unknown or stale lookup state remains explicit and reconciliation-required.
- Reconciliation-required state continues to block local paper order-plan creation.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.

## Current Limitations

- No authenticated IBKR session.
- No IBKR SDK dependency.
- No market data.
- Paper order submission is handled separately by Slice 049 and still requires fresh contract
  metadata, risk, approval, OMS, idempotency, connection-state, reconciliation, and protection
  evidence.
- No order status or fill callbacks.
- Tests use injected connectors and do not require a running TWS or IB Gateway process.
