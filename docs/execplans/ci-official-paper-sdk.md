# ExecPlan: Install the official paper SDK before CI verification

## 1. Goal

Make the published integration reproducibly verifiable on clean Windows and Ubuntu GitHub Actions runners, then publish the approved CI fix to `main`.

## 2. Non-goals

Broker connections, service restarts, paper trials, trading behavior changes, dependency upgrades, and test exclusions are outside this slice.

## 3. Safety constraints

Retain paper-only adapters, human authorization, risk checks, stale-data and unknown-state blocks, duplicate prevention, protection, and audit logging. Introduce no secrets. SDK installation must use the existing official archive checksum and packaging-only Protobuf patch; it must not connect to Gateway or transmit orders. Keep the SDK outside repository history and retain all existing verification and audit thresholds.

## 4. Current state

Integration commit `b39d590d7b5171bf0152ee610f8ee7362f7b880c` is published on `main`. Its local full gate passed with the official `ibapi 10.50.2` installed. GitHub Actions run `39780838971` failed on Ubuntu: 1,538 backend tests passed and 27 failed with `ModuleNotFoundError: No module named 'ibapi'`; the matrix canceled Windows. CI installs locked Python dependencies but omits the separately distributed SDK. README and Windows setup instructions also put SDK installation after verification. The existing `scripts/install-paper-sdk.ps1` already verifies the official archive SHA256 and applies the documented Protobuf 5.29.6 metadata pin. The user explicitly approved adding this installer to both CI jobs, correcting setup order, verifying, and pushing.

## 5. Proposed design

Add one shared matrix step, using PowerShell Core on both hosted platforms, immediately after backend dependency installation. Invoke the existing SDK installer and check installed Python dependency consistency. Move the SDK installation before verification in both setup entry points and explain that offline adapter tests need its classes. Reuse the installer and existing adapter tests rather than introducing another download path or weakening tests.

## 6. Data model changes

None.

## 7. API changes

None.

## 8. Test plan

Use the existing failing adapter tests as the regression evidence. Install the SDK into an isolated clean Python environment and check its version, imports, and dependency consistency. Complete the local full gate already running on the published source and verify that the final source fingerprint remains valid. Run the complete Windows and Ubuntu CI matrix for the fix commit, inspect failures if any, and retain secret scanning and dependency audits.

## 9. Verification commands

From the repository root: `python -m venv .tmp/ci-sdk-verification`; with that environment first on PATH, `./scripts/install-paper-sdk.ps1`, `python -m pip check`, and `python -c "from ibapi.client import EClient; from ibapi.order import Order; import importlib.metadata; print(importlib.metadata.version('ibapi'))"`. Complete `./scripts/verify.ps1` in the existing full verification environment. Run `git diff --check`, `python scripts/verify_repo.py`, and `python scripts/secret_scan.py`; push normally and inspect the complete CI matrix with `gh run view`.

## 10. Rollback plan

Retain the integration branch, original stash, and published integration commit. Revert a faulty CI fix with a new commit; do not rewrite remote history or change local broker state. A failed CI result blocks reporting successful publication verification.

## 11. Implementation steps

1. Record the diagnosed failure and approved scope in this plan before implementation.
2. Add the existing installer to both matrix jobs and fix the documented install order.
3. Verify clean SDK installation, finish local checks, and review the diff for scope and safety.
4. Commit and push the fix normally; check both CI platforms and record actual outcomes.

## 12. Completion criteria

Both CI platforms install the checksum-verified official SDK before tests, documentation gives the same correct ordering, local checks pass, the fix is published, and Windows and Ubuntu CI succeed for the published commit. The original stash remains recoverable and no broker operation occurs.

## 13. Risks and assumptions

Hosted runners must have PowerShell Core and access to the official pinned archive. Archive drift must fail checksum validation rather than accept new bytes. Local installation alone cannot establish hosted Linux behavior; both remote jobs are required. Offline tests and CI do not establish real Gateway fill or protective-order qualification.

### Local verification and review, 22 October 2026

Implemented the shared CI installer step and corrected README/Windows setup ordering. An isolated clean Python environment successfully installed `ibapi 10.50.2` and `protobuf 5.29.6` with the existing checksum-verified installer; importing `EClient` and `Order` succeeded and `pip check` reported no broken requirements. No SDK files were added to repository history.

The full local `./scripts/verify.ps1` rerun reached `verify: ok` at 23:57 Sydney time: 1,565 backend tests, 190 frontend unit tests and 29 browser tests passed, together with formatting, lint, types, build, secret scanning and both dependency audits. Python and npm audits reported no known vulnerabilities. The source/build fingerprint is `47cd60eea0d5da1cbde023293ddc56a0b3d49a630feb7095a58c27ba4524d1a3`; the record retains `paper_trials: false`. Switching to local main caused Git's Windows line-ending conversion and invalidated the earlier byte-level stamp; this complete rerun verifies the current checkout.

Diff self-review found only the CI installation step, setup ordering/explanation and this plan. Existing tests directly cover the missing SDK dependency; no test skips, protocol changes, audit suppression or trading changes were introduced. Secret scanning and `git diff --check` passed. Publication and the complete hosted CI results remain the final checks for this slice.
