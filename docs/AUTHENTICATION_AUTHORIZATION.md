# Authentication And Authorization

Slice 054 adds a local operator authentication and authorization foundation. Slice 055 hardens the
local role policy for approval and administration separation. Slice 056 uses the same local
authorization model for emergency stop controls.

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

with the local `admin` role. Slice 055 keeps that local admin useful for read and workflow
administration work, but the local admin role cannot approve or reject simulation tickets.

Optional local request headers can be used in tests and local inspection:

```text
x-operator-id
x-operator-roles
```

Only non-secret operator identifiers and role names are allowed. Secret-shaped operator values are
rejected. Production mode rejects local header authentication rather than silently treating it as a
real identity provider.

## Permissions

The permission set is intentionally small:

| Permission | Purpose |
| --- | --- |
| `view_operations` | Read safe operational views. |
| `approve_simulation` | Approve or reject simulation approval tickets only. |
| `administer_system` | Create/update local workflow definitions and start saved simulation workflow runs. |

Slice 055 binds these permissions to separated local roles.

## Role Policy

Slice 055 defines three local roles:

| Role | Permissions |
| --- | --- |
| `viewer` | `view_operations` |
| `approver` | `view_operations`, `approve_simulation` |
| `admin` | `view_operations`, `administer_system` |

The approval role policy is:

- simulation approval and rejection require the dedicated `approver` role;
- the local `admin` role cannot approve or reject simulation tickets;
- a local identity cannot combine `admin` and `approver` roles;
- `approver` cannot create/update workflow definitions or start saved workflow simulation runs;
- `admin` remains able to administer local workflow definitions and saved simulation workflow runs.

This is local role hardening only. It is not production authentication, it does not create live
trading approval, and it does not add broker or credential controls.

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
- emergency stop activation/deactivation endpoints require `administer_system`;
- approval and emergency stop mutation body `actor` values must match the authenticated operator
  id.

Approval endpoints remain simulation-only. Workflow execution remains simulation-only. No route in
Slice 054 can transmit a live order or connect to a live broker.

Emergency stop endpoints remain local application controls only. Activating the local emergency stop
does not connect to a broker, cancel live orders, flatten positions, liquidate positions, or
transmit orders.

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
- operator roles;
- required role;
- role-separation policy;
- allowed or denied result;
- reason.

It does not record passwords, tokens, identity-provider secrets, broker credentials, account
identifiers, broker hosts, or broker ports.

## Production Boundary

Production-like paper operation still requires later approved work:

- Slice 057 observability, retention, backup, and incident response;
- Slice 058 live-readiness evidence dashboard;
- Slice 059 controlled paper-production rollout checklist;
- external review and explicit human approval.

Local auth must not be treated as sufficient for production rollout.
