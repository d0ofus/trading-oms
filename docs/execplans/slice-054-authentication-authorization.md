# ExecPlan: Slice 054 Authentication And Authorization

## 1. Goal

Add a local, typed operator authentication and authorization foundation so the app can identify an
operator, evaluate view/approval/admin permissions, and audit privileged authorization decisions
without adding real credentials, external identity-provider secrets, production rollout, or live
trading behavior.

## 2. Non-goals

- Production rollout.
- External identity-provider integration.
- Password, cookie, OAuth, bearer-token, API-key, certificate, private-key, or secret handling.
- Real operator onboarding.
- Broker credential storage.
- Broker host or port controls.
- IBKR live trading.
- Live account mode.
- Order transmit, submit-live, route-live, cancel, modify, or market-data subscription controls.
- Slice 055 role separation-of-duties hardening.
- Slice 056 emergency stop, Slice 057 observability/backup, Slice 058 evidence dashboard, or
  Slice 059 rollout checklist work.

## 3. Safety constraints

- Live trading remains disabled.
- Default app posture remains paper or simulation.
- No live broker order path may be introduced.
- No real secrets, credentials, account identifiers, passwords, certificates, private keys, tokens,
  API keys, or external identity-provider values may be committed, logged, rendered, exported, or
  documented as real values.
- IBKR TWS or Gateway ports must not be exposed.
- Local auth must not become production auth. Production-like operation still requires later
  approved authentication provider design, external review, emergency stop, observability, and
  controlled rollout evidence.
- Approval mutation endpoints must stay simulation-only and continue to depend on risk, approval,
  OMS, audit, idempotency, and reconciliation gates.
- Authorization decisions for privileged actions must be journaled where practical.

## 4. Current state

The repo has:

- safe configuration defaults with live trading disabled;
- read APIs for safety, audit events, signals, risk decisions, approval tickets, orders, positions,
  alerts, readiness, and paper trading;
- simulation approval mutation endpoints;
- workflow definition and workflow simulation mutation endpoints;
- append-only JSONL event journaling;
- frontend read API loading and a paper/simulation operations shell;
- no operator identity model, no permission model, no authorization checks, and no auth status UI.

Slice 053 added deployment and secrets-management planning only. Slice 054 is the next not-started
slice and is explicitly approved for implementation.

## 5. Proposed design

Add a local auth module:

- `OperatorIdentity` with safe operator id, local authentication state, local method, roles, and
  derived permissions.
- `OperatorSessionReadModel` for backend/frontend inspection of the current operator session.
- `AuthzDecision` records for allow/deny decisions.
- local development/test header support for non-secret operator id and roles.
- production local-auth rejection so header-based local identity cannot be treated as production
  authentication.

Add FastAPI authorization helpers:

- read endpoints require `view_operations`;
- approval approve/reject endpoints require `approve_simulation`;
- workflow create/update and workflow simulation run endpoints require `administer_system`;
- each allow/deny permission decision is appended to a local auth journal;
- approval request actor must match the authenticated operator identity.

Add frontend visibility:

- load `GET /api/operator-session`;
- show operator access state and permissions;
- keep fallback local, non-secret, paper/simulation safe;
- render no login, password, token, broker, or live-trading controls.

Add docs and tests covering safe auth behavior, denied permissions, journal records, production
local-auth rejection, frontend visibility, and forbidden secret/live/broker affordances.

## 6. Data model changes

New in-memory/read-model objects only:

- `OperatorIdentity`
- `AuthzDecision`
- `OperatorSessionReadModel`

No database tables or migrations.

## 7. API changes

New read-only endpoint:

```text
GET /api/operator-session
```

Existing endpoints add permission checks but do not change their success payloads.

No new order, broker, IBKR, market-data, credential, password, token, login, logout, or production
deployment endpoints are added.

## 8. Test plan

- Backend unit tests for local operator identity, role-to-permission derivation, invalid role
  rejection, production local-auth rejection, permission allow/deny decisions, and journal records.
- Backend read-model/API tests for `GET /api/operator-session`, view permission checks, denied
  approval/admin permissions, actor mismatch rejection, and forbidden secret/live/broker affordance
  keys.
- Frontend API client tests for loading operator session via `GET`.
- Frontend UI tests for operator access visibility and absence of login/password/token/live/broker
  controls.
- Documentation tests or updates where practical to prove Slice 054 ready state and Slice 055+
  not-started boundaries.
- Full verification.

## 9. Verification commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 054 branch changes. No external identity provider, secrets, deployment resources,
database migrations, broker sessions, live order paths, or production resources are introduced.

## 11. Implementation steps

1. Add focused auth/authz backend tests.
2. Implement the local operator auth module.
3. Add `OperatorSessionReadModel` and read API support.
4. Add FastAPI authorization checks and auth journal helpers.
5. Add frontend operator session types, fallback, API loading, UI visibility, and tests.
6. Add auth docs and update slice/security/readiness docs.
7. Run full verification.
8. Self-review for trading safety, secret leakage, auth bypass, live-order prevention, scope creep,
   and Slice 055+ leakage.
9. Commit and push a Slice 054 branch if possible; otherwise report exact manual commands.

## 12. Completion criteria

- Slice 054 ExecPlan exists.
- Typed operator identity and permission models exist.
- Read/view, simulation approval, and administration permission checks exist on safe in-scope
  backend surfaces.
- Privileged authorization decisions are journaled where practical.
- Default development/test use remains usable without real credentials or external IdP secrets.
- Production local-auth fallback is explicitly rejected.
- Frontend shows operator auth state and permissions without rendering credential, token, live,
  broker, or production controls.
- Docs describe the auth foundation and hard stops.
- `docs/SLICES.md` marks Slice 054 ready for human review while Slice 055+ remain not started.
- Full verification passes.

## 13. Risks and assumptions

- The local header-based auth foundation is not production authentication and must not be treated as
  sufficient for rollout.
- Default local development uses a permissive local operator to keep existing flows usable; Slice
  055 can harden separation of duties after this foundation lands.
- Requiring admin permission for workflow mutation endpoints is an initial administrative boundary,
  not the final production role model.
- Future auth work must choose a real provider or self-hosted identity mechanism without committing
  secrets or weakening trading safety gates.
