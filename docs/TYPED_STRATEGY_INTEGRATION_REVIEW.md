# Selective typed strategy integration review

## Base and preservation

The integration branch starts at GitHub main `0d1224b275ed52a4c1df0c48fc6f66a83b9311d1`.
A fresh fetch on 2026-09-15 confirmed that main still points to that commit. The original
`trading-oms` folder is preserved. Its verified source archive and SHA-256 manifest are at
`../trading-oms-backups/20260914-162833/` relative to the integration checkout.

The local committed Slice 058 tree matched the version already merged into GitHub. The useful
new work was the uncommitted typed builder. A direct replacement would have overwritten newer
v1 approval/execution persistence, recovery, projections, comparison and audit behavior. Typed
modules and routes were therefore added beside the main implementations.

## Review findings resolved

| Finding | Integrated behavior and evidence |
| --- | --- |
| Accepted stop wiring did not determine the executed stop | Backend and frontend reject unsupported topology; regression rewires the protective-stop price input |
| Interrupted final persistence could append another fill on retry | Durable reservation precedes execution; injected failure before completion and independent-service retry cannot add fills |
| Completed result could be served without its journal | Saved payload and exact journal manifests are validated on every run read/retry; missing and altered evidence tests fail closed |
| Stale editor could replace newer work | Expected-version saves and transactional head checks; UI retains the version loaded and does not silently retry |
| Risk sized at the trigger could exceed the budget at entry | Quantity is reduced and actual entry notional is rechecked before the simulated fill |
| Client timing or historical arm time could keep expired authorization usable | Service uses its clock; API uses server time, including the expiry boundary |
| Changed request could be treated as an exact completed retry | Reservation journals the risk/reconciliation inputs and completed retries must match |
| Administrator could combine execution privileges | Administrator and strategy-operator roles remain separated; endpoint and role tests cover denial |
| Protection stopped at the entry session | All remaining supplied ticks are monitored; later-session gap and time-exit regressions cover the behavior |

The API also rejects implicit/coerced reconciliation, preserves strict typed request shapes, and
connects emergency activation/clear to persisted typed state without reviving old authorizations.

## Verification and limits

The required `./scripts/verify.ps1` gate covers repository safety checks, Python formatting/lint,
compilation, all backend tests, frontend lint/type checks/tests, and the resilience subset. The
integration also runs `npm.cmd --prefix frontend run build` and `git diff --check`.

The final gate passed **767 backend tests**, **188 frontend tests**, and the four-test resilience
rerun, with all formatting, lint, compilation and type checks passing. The frontend build succeeds
with a warning about a 591.20 kB minified JavaScript chunk. The backend emits a Starlette/httpx
deprecation warning. `git diff --check` and integration Git connectivity checks pass. All 265
original source files still match the backup manifest; the bounded scan of all 32 integration
paths found no credential patterns or enabled-live settings.

Browser visual verification was attempted, but the computer-use tool returned **No browser is
available** and an empty browser inventory. Static rendering tests cover both builder sections;
interactive layout and browser input testing remain a manual follow-up. The local QA servers were
isolated from normal application state and are stopped after checks.

This is a local simulation integration, not evidence of broker correctness, live readiness, or an
independent safety review. No SDK, credentials, order transport, external alert delivery, deployment,
or changes to Candidate 062/063 review packets were added. Existing v1 paths and their tests remain
in place. Typed results use separate storage and do not feed v1 comparison/projections.

On 2026-09-15 the user authorized publishing this integration and consolidating the project on
main. The follow-up [publication and consolidation plan](execplans/publish-and-consolidate-main.md)
covers checked PR merge, verified backups, branch cleanup and the canonical working directory.
Browser review remains a follow-up check; no deployment or additional trading slice is included.
