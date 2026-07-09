# IBKR Paper Connectivity Probe

Slice 047 adds a local-only IBKR paper connectivity probe behind the existing IBKR adapter
boundary.

The probe is a TCP reachability check for a validated local TWS or IB Gateway paper endpoint. It is
not an IBKR protocol session and is not evidence that an account, contract, market-data stream, or
order path is ready.

## Scope

The probe can:

- validate the existing paper-only adapter configuration;
- check whether the configured localhost paper endpoint accepts a short TCP connection;
- close the connection without sending application data;
- journal a probe result;
- journal the corresponding adapter connection-state observation;
- mark timeout or unexpected OS errors as `unknown_requires_reconciliation`.

The probe cannot:

- authenticate;
- store account identifiers;
- use credentials, tokens, passwords, certificates, private keys, or secrets;
- import or use an IBKR SDK;
- subscribe to market data;
- perform contract lookup itself;
- place, submit, transmit, route, cancel, or modify orders;
- register SDK/network order status listeners;
- register SDK/network fill listeners;
- expose public IBKR ports;
- enable live trading.

## Configuration Boundary

The probe uses `IbkrPaperAdapterConfig`, which remains:

- `account_mode: paper`;
- `live_trading_enabled: false`;
- localhost-only host values;
- known paper ports only: `7497` for TWS paper or `4002` for IB Gateway paper.

No new config keys, arbitrary host fields, account fields, credential fields, live-mode fields, API
endpoints, workflow nodes, or UI controls are added.

## Journal Events

Each probe appends:

```text
ibkr.paper.connectivity_probe.recorded
```

The adapter then appends the existing connection-state event:

```text
ibkr.paper.connection_state.recorded
```

Probe payloads include:

- probe ID;
- timestamp;
- safe reason;
- endpoint kind: `tws_paper` or `gateway_paper`;
- probe status;
- resulting adapter connection state;
- reconciliation flag;
- optional failure category.

Probe payloads intentionally exclude host, port, account, credential, route, submit, transmit, and
secret fields.

## Status Mapping

| Probe outcome | Probe status | Adapter state | Reconciliation |
| --- | --- | --- | --- |
| Local paper endpoint accepts TCP connection | `reachable_local_paper_endpoint` | `connected_paper` | `false` |
| Local paper endpoint refuses TCP connection | `unreachable_local_paper_endpoint` | `disconnected` | `false` |
| Timeout or unexpected OS error | `unknown_requires_reconciliation` | `unknown_requires_reconciliation` | `true` |

## Safety Guarantees

- Live trading remains disabled.
- No paper order transport is added.
- No order placement path is added.
- The probe itself performs no market-data or contract lookup work.
- Unknown state remains explicit and blocks local paper order-plan creation.
- Core OMS, risk, approval, workflow, and strategy modules remain broker-agnostic.

## Current Limitations

- TCP reachability does not prove an authenticated IBKR session.
- TCP reachability does not prove an account is paper, present, or ready.
- TCP reachability does not prove contract lookup or order transport readiness.
- Tests use injected connectors and do not require a running TWS or IB Gateway process.
