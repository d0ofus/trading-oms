# ExecPlan: Slice 055 Operator Roles And Approval Permissions

## 1. Goal

Harden the local operator role model so simulation approval is a dedicated operator duty, system
administration is separate from approval, and approval authorization decisions produce explicit
audit evidence without adding production authentication, secrets, broker controls, or live trading.

## 2. Non-goals

- Production rollout.
- External identity-provider integration.
- Passwords, bearer tokens, cookies, OAuth, API keys, certificates, private keys, account IDs, or
  real credentials.
- Live trading approval.
- Broker connectivity changes.
- Emergency stop implementation.
- Observability, backup/restore tooling, incident response, or rollout automation.

## 3. Safety constraints

- Live trading remains disabled.
- Default app posture remains paper or simulation.
- Approval endpoints remain simulation-only.
- No route may transmit, submit, route, cancel, or modify a live broker order.
- No secrets, account identifiers, broker hosts, broker ports, tokens, passwords, certificates,
  private keys, or credential material may be added to repo files, logs, docs, tests, UI, or audit
  payloads.
- Local header auth remains local development/test auth only and must not become production auth.
- Approval permission must require a dedicated approver role and must stay separated from system
  administration.
- Privileged role decisions must be journaled without secret or broker affordances.

## 4. Current state

Slice 054 added local typed operator identity, roles, derived permissions, `GET
/api/operator-session`, route-level authorization checks, and local authorization decision journal
records. The current role mapping still grants the default local `admin` role both approval and
administration permissions, leaving separation of duties as future Slice 055 work.

## 5. Proposed design

- Keep `viewer`, `approver`, and `admin` roles.
- Grant `viewer` read-only operations visibility.
- Grant `approver` read-only visibility plus simulation approval/rejection permission.
- Grant `admin` read-only visibility plus workflow/system administration permission, but not
  simulation approval permission.
- Reject local identities that combine `admin` and `approver` roles.
- Include safe role-policy evidence in authorization decision journal records.
- Link approval authorization evidence to the specific approval ticket resource.
- Update operator-session read models and UI visibility so operators can see the approval role
  policy without exposing credential or broker controls.

## 6. Data model changes

- Extend local operator-session inspection payloads with safe role-policy fields only.
- Extend local authorization decision payloads with operator roles, required role, and separation
  policy evidence.
- No database migrations.

## 7. API changes

- No new endpoints.
- Existing `GET /api/operator-session` response gains safe inspection fields for role policy.
- Existing simulation approval endpoints continue to require approval permission and remain
  simulation-only.

## 8. Test plan

- Unit tests for role-permission derivation, admin/approver separation, and mixed-role rejection.
- API tests proving admin cannot approve simulation tickets, approver can approve/reject, approver
  cannot administer workflows, and authorization denials are journaled with role evidence.
- Read-model and frontend tests proving operator-session policy is visible without credential,
  broker, account, token, or live-trading affordances.
- Documentation tests for Slice 055 safety hard stops.

## 9. Verification commands

```powershell
.\scripts\verify.ps1
```

## 10. Rollback plan

Revert the Slice 055 commit. That restores Slice 054 local auth behavior while preserving the
existing no-live-trading and no-secret safety gates.

## 11. Implementation steps

1. Add focused failing backend and frontend tests for role separation and approval evidence.
2. Update the local operator role mapping and validation.
3. Add safe role-policy fields to authorization decisions and operator-session read models.
4. Update approval route resources and UI operator access/approval affordances.
5. Update docs and Slice 055 status.
6. Run full verification and self-review.

## 12. Completion criteria

- Admin role does not grant simulation approval.
- Approver role grants simulation approval but not administration.
- Mixed admin+approver local identities are rejected.
- Approval allow/deny decisions are journaled with role-policy evidence and ticket resource.
- UI shows role policy and disables simulation approval actions when the current operator cannot
  approve.
- No production auth, secrets, live trading, broker controls, or production rollout behavior is
  added.
- Verification passes.

## 13. Risks and assumptions

- This intentionally makes the default local admin unable to approve simulation tickets unless tests
  or local requests supply the dedicated approver role.
- Production authentication remains future approved work; this slice hardens local role semantics
  only.
