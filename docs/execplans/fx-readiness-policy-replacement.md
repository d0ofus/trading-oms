# ExecPlan: Clear FX readiness and inline policy replacement

## 1. Goal

Implement the approved inline replacement of older stock/FX funding bindings and
neutral FX waiting presentation in the existing authorization dialog.

## 2. Non-goals

Live trading, changed signal logic, automatic arming/archival, quantity conversion,
different freshness thresholds, new strategy schemas or rewriting historical bindings.

## 3. Safety constraints

Paper-only guards and one explicit final authorization remain. Replacement is a
nonexecuting preparation operation; all source runs must be disarmed, flat and clear
of unresolved broker/reservation/protection work. Preserve exact quantities including
0.01 AUD, routes, protection and optional limits. Stale observations never dispatch.
No secrets or raw account identifiers in audit payloads.

## 4. Current state

The saved AUD.USD run predates broker_credit_v1/quiet_fx_v1. Current preparation opts
into those policies, but review offers no adoption action. Readiness rendering styles
all failed checks as warnings, including healthy quiet feeds. Preparation retains an
incorrect unconditional no-borrowing statement. The inspection baseline is 32 tests.

## 5. Proposed design

Extract pure run construction from persistence/data scheduling. Add authenticated,
transactional, idempotent replacement using the shared binding/compatibility logic.
Record source/target links without changing source bindings. Reuse unchanged linked
targets across retries and concurrent reviews. Recheck source ownership and material
terms at confirmation. Existing preparation handles changed requirements with prefill.

Separate established feed/history health from execution freshness in responses and
the stable review row. Neutral execution waiting never changes eligibility semantics.
Make funding language policy-aware; expose appropriate preparation/diagnostic actions.

## 6. Data model changes

Add replacement link/receipt/policy-installation documents and audited events. No
existing strategy, run, approval or incident migration. Back up before installation.

## 7. API changes

POST /api/runs/policy-replacement accepts one to five source IDs, expected binding
hashes, target policy revision and mutation ID. Return source/target links and review
IDs. Arming previews expose replacement eligibility, blockers and existing links.
Readiness adds feed health and execution-state detail without replacing passed or
authorization_ready. Existing clients keep their original binding semantics.

## 8. Test plan

Regressions first for legacy funding, exact preservation, duplicate/concurrent requests,
atomic batch failure, changed source state, exposure and broker reconciliation. Test
independent quote streams, neutral quiet status and unchanged dispatch guards. Browser
coverage includes inline replacement, prefilled fallback, one final review, stable DOM,
poll cleanup, keyboard behavior and existing canvas/navigation.

## 9. Verification commands

Focused pytest/frontend/browser checks, then ./scripts/verify.ps1. Follow with a
data-only AUD.USD observation correlating source/receipt timestamps and readiness.

## 10. Rollback plan

Disable new replacement preparation with a dedicated rollback switch. Existing run
policies, reconciliation, protection, exits and history remain managed normally.

## 11. Implementation steps

1. Add failing backend regressions.
2. Implement pure construction and transactional replacement with API coverage.
3. Separate feed health/freshness; integrate inline review and preparation prefill.
4. Add browser regressions and operator documentation.
5. Safety review, full gate and data-only observation.

## 12. Completion criteria

Approved workflow implemented, full gate passes, current-build verification recorded,
no production run replaced/armed and no order sent during acceptance observations.

## 13. Risks and assumptions

Preserve the dirty workspace from prior tasks. Do not infer margin permission from a
subscription. Policy adoption creates a new binding without republishing strategies.
An unchanged existing replacement can be reused only while inactive and eligible.
Unknown/failed feeds retain blockers; a healthy quiet feed is not an incident.

## Progress

- ExecPlan created before implementation.
- Added failing legacy-binding/replacement/feed-status regressions before implementation.
- Implemented transactional replacement, authenticated API, rollback switch, inline review
  selection, existing preparation prefill and policy-aware borrowing terms.
- Added independent feed health/execution freshness without changing dispatch checks.
- 24 focused replacement/readiness regressions pass, including concurrent requests,
  rollback after a partial transaction, restart, API authentication and four stock templates.
- Isolated browser workflows pass for FX settings/canvas, neutral stable waiting rows,
  inline replacement, preserved 0.01 AUD and original history, prefill and polling cleanup.
- Full `scripts/verify.ps1` passed: 1,384 backend tests, 190 frontend tests and
  25 browser tests; formatting, lint, typing, secret scan and dependency audits passed.
  The exact current source/build verification fingerprint was recorded.
- Safety review confirmed no adapter transmission changes, automatic arming, quantity
  conversion, historical binding edits or dispatch-freshness relaxation. The first
  replacement transaction backs up state and records authenticated links/receipts.
- A final isolated GatewayData observation (execution disabled) was attempted on
  2026-09-24. The configured paper endpoint 127.0.0.1:4002 actively refused connections.
  No paper handshake or quote timestamps could be obtained, and no orders were created.
  Live callback/readiness correlation remains an external acceptance limitation until
  the existing paper Gateway is available. No broker setting or production run changed.
