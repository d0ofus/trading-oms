# Authentication And Authorization

Slice 054 adds a local operator authentication and authorization foundation.

This is not production authentication.

It does not add passwords, bearer tokens, cookies, OAuth, API keys, certificates, private keys,
identity-provider secrets, broker credentials, account identifiers, live trading, live account mode,
production rollout, or broker control surfaces.

## Local Operator Model

The backend defines a typed local operator identity with:

- `operator_id`;
- local authentication state;
- local authentication method;
- roles;
- derived permissions;
- explicit booleans for view, approval, and administration capability.

Default development and test mode use the local operator:

```text
human-operator-001
```

with the local `admin` role. This keeps local development usable while later slices harden
production identity, separation of duties, and operator approval permissions.

Optional local request headers can be used in tests and local inspection:

```text
x-operator-id
x-operator-roles
```

Only non-secret operator identifiers and role names are allowed. Secret-shaped operator values are
rejected. Production mode rejects local header authentication rather than silently treating it as a
real identity provider.

## Permissions

The Slice 054 permission set is intentionally small:

| Permission | Purpose |
| --- | --- |
| `view_operations` | Read safe operational views. |
| `approve_simulation` | Approve or reject simulation approval tickets only. |
| `administer_system` | Create/update local workflow definitions and start saved simulation workflow runs. |

These permissions are a foundation. Slice 055 remains responsible for role hardening, separation of
duties, and final approval-permission policy.

## API Boundaries

New read-only endpoint:

```text
GET /api/operator-session
```

The response is inspection data only. It contains no secrets, credential handles, account
identifiers, broker hosts, broker ports, live-mode fields, or action URLs.

Existing route checks:

- read endpoints require `view_operations`;
- simulation approval approve/reject endpoints require `approve_simulation`;
- workflow definition create/update and saved workflow simulation start require `administer_system`;
- approval decision body `actor` must match the authenticated operator id.

Approval endpoints remain simulation-only. Workflow execution remains simulation-only. No route in
Slice 054 can transmit a live order or connect to a live broker.

## Audit Records

Backend authorization decisions append local journal records with event type:

```text
authz.decision.evaluated
```

The journal payload records:

- operator id;
- requested permission;
- resource;
- action;
- allowed or denied result;
- reason.

It does not record passwords, tokens, identity-provider secrets, broker credentials, account
identifiers, broker hosts, or broker ports.

## Production Boundary

Production-like paper operation still requires later approved work:

- Slice 055 operator roles and approval permissions;
- Slice 056 emergency stop;
- Slice 057 observability, retention, backup, and incident response;
- Slice 058 live-readiness evidence dashboard;
- Slice 059 controlled paper-production rollout checklist;
- external review and explicit human approval.

Local auth must not be treated as sufficient for production rollout.
