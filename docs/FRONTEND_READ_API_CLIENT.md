# Frontend Read API Client

Slice 022 adds a typed frontend client for the read-only backend API.

Slice 023 wires the main UI shell to this client. The client does not add mutation calls, approval
action UI, order submission UI, broker connection UI, credential fields, or live trading.

## Client Module

The client module is:

```text
frontend/src/readApiClient.ts
```

It provides typed `GET` functions for:

- `/api/safety`
- `/api/audit-events`
- `/api/signals`
- `/api/risk-decisions`
- `/api/approval-tickets`
- `/api/orders`
- `/api/positions`
- `/api/alerts`
- `/api/readiness`

The aggregate loader fetches all sections into a single operations snapshot for future UI wiring.

## Loading States

The frontend read state is explicit:

- `loading`: no backend data has been loaded yet;
- `loaded`: backend read data is available;
- `empty`: backend is reachable but workflow record lists are empty;
- `error`: backend read API is unavailable and the UI should show a safe local fallback.

The error state intentionally returns a conservative fallback snapshot with:

- paper mode;
- live trading disabled;
- broker connectivity not configured;
- readiness not ready;
- no workflow records.

Error text is generic and does not echo arbitrary exception messages, URLs, tokens, credentials, or
operator-provided values.

## Safety Guarantees

- The client uses `GET` requests only.
- No submit, approve, reject, cancel, connect, transmit, credential, token, password, account,
  host, port, route, socket, or secret affordance keys are exposed.
- No broker SDK or socket code is added.
- No live trading or order submission path is added.

## Current Limitations

- The main UI shell consumes this client as of Slice 023.
- The backend data source remains the static demo read model until later persistence/orchestration
  slices.
