# ExecPlan: Resolve dependency vulnerabilities and publish to GitHub main

## 1. Goal

Remove the reported Python dependency vulnerabilities, verify the complete
application, and publish the existing workspace improvements and security fixes
to `d0ofus/trading-oms` on `main` in two separately reviewable commits.
The user approved this plan and publication of both change sets on 2026-10-21.

## 2. Non-goals

No new trading features, live trading, broker orders, notification delivery,
database migrations, running-service changes, broad dependency upgrades or
verification bypasses.

## 3. Safety constraints

Preserve paper/simulation defaults, human approval, risk checks, protection,
duplicate prevention, stale-data blocking, reconciliation and journaling.
Use an isolated Python environment; do not change the shared interpreter or
restart the operating service. Never commit secrets, runtime databases, captures,
temporary environments or generated verification artifacts. Never force-push.

## 4. Current state

Local and GitHub `main` match at
`03bef165f4d786f24d3a1dfa86a6f0051f91c759`. The prior local gate passed
857 backend tests, 188 frontend tests, browser checks, build and secret scanning,
then stopped at four Python vulnerabilities in AnyIO and Certifi. Later npm
auditing and final verification recording were not reached.

An ignored baseline manifest records the original status and SHA256 of every
existing unpublished file. The exact 38-file publication inventory is:

```text
GETTING_STARTED_WINDOWS.md
README.md
backend/src/trading_oms_backend/workspace/api.py
backend/src/trading_oms_backend/workspace/broker.py
backend/src/trading_oms_backend/workspace/engine.py
backend/src/trading_oms_backend/workspace/graph.py
backend/src/trading_oms_backend/workspace/market.py
backend/src/trading_oms_backend/workspace/protection.py
backend/src/trading_oms_backend/workspace/replay_oms.py
backend/src/trading_oms_backend/workspace/store.py
backend/tests/test_workspace_api.py
backend/tests/test_workspace_broker.py
backend/tests/test_workspace_market.py
backend/tests/test_workspace_protection.py
docs/PAPER_OPERATOR_GUIDE.md
frontend/e2e/workspace.spec.ts
frontend/e2e/workspace.spec.ts-snapshots/arming-blocked-win32.png
frontend/e2e/workspace.spec.ts-snapshots/setup-dark-win32.png
frontend/e2e/workspace.spec.ts-snapshots/setup-light-win32.png
frontend/e2e/workspace.spec.ts-snapshots/studio-canvas-win32.png
frontend/e2e/workspace.spec.ts-snapshots/studio-guided-win32.png
frontend/src/workspace/ArmReview.tsx
frontend/src/workspace/Studio.tsx
frontend/src/workspace/Workspace.tsx
frontend/src/workspace/api.ts
frontend/src/workspace/workspace.css
scripts/workspace_e2e_server.py
backend/src/trading_oms_backend/workspace/diagnostics.py
backend/src/trading_oms_backend/workspace/health_file.py
backend/src/trading_oms_backend/workspace/operations.py
backend/src/trading_oms_backend/workspace/paper_test.py
backend/src/trading_oms_backend/workspace/sessions.py
backend/tests/test_workspace_flexible_sessions.py
backend/tests/test_workspace_session_operations.py
docs/PAPER_FLEXIBLE_SESSIONS_REVIEW.md
docs/execplans/paper-diagnostics-and-flexible-sessions.md
frontend/src/workspace/ConnectionTest.tsx
frontend/src/workspace/IncidentRecovery.tsx
```

## 5. Proposed design

Change only `anyio==4.14.1` to `anyio==4.14.2` and
`certifi==2026.6.17` to `certifi==2026.10.19` in the Python lock file.
Both replacement releases support Python 3.12, are not yanked and had no
vulnerabilities listed in their PyPI metadata during planning. A resolver dry run
succeeded. Confirm remediation through the unchanged repository audit command.
Keep Python direct dependencies, all other Python pins, audit thresholds and
verification scripts unchanged. Record new evidence separately from historical
review records.

Implementation finding on 2026-10-21: the first complete attempt reached npm
auditing and exposed two additional vulnerable packages that the previous failed
Python gate had not reached. Under the approved additional-findings provision,
patch the direct Vite pin from 8.3.0 to 8.3.4 and its locked source-map-js
dependency from 1.2.1 to 1.2.2. These address the source-map indexed-offset advisory
and Vite's bundled launch-editor advisories. Keep every other direct frontend
dependency pinned unchanged; do not run a forced or broad audit fix. Inspect
lock-file changes, install reproducibly with npm ci, audit early, then rerun the
complete gate. Include this narrowly required frontend remediation in the second
security commit.

The final staged whitespace check also exposed CRLF bytes in six previously
untracked Python/documentation files. Add explicit text attributes for only those
six paths and renormalize their index entries. This preserves every original
working-file byte and the successful source/build fingerprint while storing
normalized Git text. Include this small publication fix with the feature commit;
do not change whitespace thresholds or historical evidence attributes.

## 6. Data model changes

None for dependency remediation. Preserve the existing unpublished compatibility
behavior without expanding it.

## 7. API changes

None for dependency remediation. Publish the already implemented session,
diagnostic and recovery interfaces without additional features.

## 8. Test plan

Install the complete lock and editable backend in a fresh isolated environment;
run dependency consistency and an early vulnerability audit. Run the full gate:
backend, replay, risk, OMS, protection, sessions, recovery, frontend, browser,
accessibility, visual comparison, build, secret scan and both dependency audits.
Do not regenerate visual baselines or add version-string assertion tests.
Self-review all publication changes and fix P0/P1 findings. Require both Windows
and Ubuntu GitHub CI jobs to pass for the final published commit.

## 9. Verification commands

From the repository root, with the isolated environment first on PATH:

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pip check
python -m pip_audit --disable-pip --no-deps -r backend/requirements-lock.txt
.\scripts\verify.ps1
git diff --check
```

The full gate must reach `verify: ok`, including npm auditing and the current
source/build fingerprint. Record actual commands and results in the remediation
review; never claim broker trials from automated evidence.

## 10. Rollback plan

Preserve existing files and correct failures locally without resets or discarded
work. After publication, use ordinary revert commits if necessary and retain
security fixes wherever possible. Do not rewrite published history or restore a
runtime database as part of this source update.

## 11. Implementation steps

1. Save this plan and the baseline inventory before implementation edits.
2. Apply the two pins; create `.tmp/dependency-remediation-venv` using Python 3.12.
3. Install, check dependencies, audit early, then run the complete gate.
4. Self-review safety and scope; record new verification evidence separately.
5. Inspect and commit the 38 existing files plus their narrow text attributes as
   `Add paper session scheduling and operator diagnostics`.
6. Commit the lock change, this plan and remediation evidence as
   `Patch vulnerable Python dependencies and record verification`.
7. Refresh `origin/main`; if it advanced, rebase the unpublished commits, review
   integration and rerun the complete gate.
8. Push normally with `git push origin main` and monitor CI for that exact commit.
9. Confirm remote main equals local HEAD and the working tree is clean; report
   commit links and checks. Report authentication/policy blockers without bypasses.

## 12. Completion criteria

No reported vulnerabilities; complete local gate passes; both change sets are
published; Windows and Ubuntu CI pass for the final commit; working tree is clean.
No secrets, runtime data or live-trading capability introduced. Report exact
checks, commit identities and outstanding operator paper acceptance.

## 13. Risks and assumptions

The user selected publication of both change sets. Resolve and document any new
audit findings before claiming a clean gate. This task updates repository
dependencies and the isolated verification environment. Updating/restarting the
operating service remains a separate disarmed maintenance step. Automated checks
do not replace supervised Gateway trials or five-session acceptance.

Implementation evidence is recorded separately in the
[remediation review](../DEPENDENCY_REMEDIATION_REVIEW.md), including the additional
frontend findings, final clean audits and successful local gate fingerprint.
