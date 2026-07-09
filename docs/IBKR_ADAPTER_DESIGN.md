# IBKR Adapter Design

## Status

Slice 016 implements the first local IBKR paper adapter foundation in
`trading_oms_backend.ibkr_paper_adapter`.

The current adapter validates paper-only local configuration, can run a local TCP reachability probe
against a validated localhost paper endpoint, can resolve sanitized stock contract metadata through
an injected adapter-bound connector, records local connection-state observations, builds local paper
order plans from validated `BrokerOrderRequest` records, records guarded paper submission attempts
through an injected adapter-bound connector, records correlated paper order status and fill
callbacks, and journals those records. It does not authenticate with TWS or IB Gateway by itself,
does not import an IBKR SDK, does not expose account identifiers, and does not register network
callback listeners.

## Rules

- IBKR integration must be paper-only when first introduced.
- Broker-specific behavior must live behind an adapter interface.
- Core OMS and risk logic must not import IBKR libraries directly.
- Reconnect and reconciliation must be designed before any production rollout.
- Live trading must remain disabled by default.

## Expected adapter responsibilities

Current local foundation:

- Validate paper-only, localhost-only adapter configuration.
- Probe local TWS/Gateway paper TCP reachability without sending IBKR protocol data.
- Resolve supported paper stock contract metadata through an injected adapter-bound connector.
- Record local connection-state observations.
- Represent unknown state as reconciliation-required.
- Build local non-transmitting paper order plans from validated risk-passed and approval-referenced
  order requests.
- Record guarded paper order submission attempts and outcomes only after risk, approval, OMS,
  contract, idempotency, connection-state, reconciliation, and protection checks pass.
- Record paper order status and fill callback observations only when they correlate to an accepted
  paper submission and pass idempotency, ordering, freshness, and OMS-compatible state checks.
- Emit structured local events to the event journal.

Future paper transport responsibilities:

- Establish an authenticated paper-only TWS or IB Gateway session.
- Subscribe to market data.
- Add SDK-backed contract lookup after separate review if needed.
- Reconcile open orders and positions.
- Emit structured events to the event journal.

Those future responsibilities require explicit approval in later slices and must remain paper-only
until the live-readiness checklist is complete.
