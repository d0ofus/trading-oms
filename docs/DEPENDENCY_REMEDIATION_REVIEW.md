# Dependency remediation and publication review

Date: 2026-10-21 (Australia/Sydney).

This is a code self-review and automated verification record for the approved
[dependency remediation and publication plan](execplans/dependency-remediation-and-main-publication.md).
It is not an independent review or evidence of actual paper execution. Historical
review packets and the September flexible-session verification record are preserved.

## Changes and provenance

The baseline is `03bef165f4d786f24d3a1dfa86a6f0051f91c759`. The 38 existing
unpublished workspace files are inventoried in the plan. Their bytes were checked
against an ignored SHA256 manifest and were unchanged by this remediation.

The staged check found CRLF line endings in six newly tracked Python/documentation
files, which Git's existing configuration treated as trailing whitespace. Narrow
text attributes normalize only those index entries. Their working bytes and the
verified source/build fingerprint remain unchanged; historical evidence
attributes and whitespace-check settings are preserved. The feature commit thus
contains the original 38 files plus this publication-only attributes change.

Only two Python lock-file pins changed:

| Package | Previous version | Patched version | Prior audit findings |
|---|---|---|---|
| AnyIO | 4.14.1 | 4.14.2 | PYSEC-2026-4025, PYSEC-2026-4023, PYSEC-2026-4024 |
| Certifi | 2026.6.17 | 2026.10.19 | PYSEC-2026-4320 |

Both vulnerable pins were already present in committed main. The replacements
were checked against official PyPI metadata and a resolver dry run before
installation. Python direct dependency declarations, other Python pins, audit
thresholds, verification scripts and visual baselines were not changed by this
remediation.

The first full-gate attempt passed all functional checks and the Python audit,
then stopped at two high-severity npm package findings. The approved plan requires
additional audit findings to be resolved. The targeted frontend fixes are Vite
8.3.0 to 8.3.4 and transitive source-map-js 1.2.1 to 1.2.2. All other direct frontend
pins remain unchanged; no forced audit fix or audit suppression is used.
The failing command was `npm.cmd --prefix frontend audit --audit-level=low`,
which reported `2 high severity vulnerabilities` and exit code 1.

Vite's updated dependency floors also require refreshed build-chain lock entries:
PostCSS 8.5.31, Nano ID 3.3.20, Rolldown 1.2.14, its matching platform bindings and
OXC types 0.154.0. Package inventory is unchanged; unrelated locked packages are
preserved. The manifest changes only Vite, and npm ci checks lock consistency.

The [source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)
identifies the fixed release as 1.2.2. Vite's bundled launch-editor fixes address
[Windows argument escaping](https://github.com/advisories/GHSA-698v-4r3x-3vcv),
[editor argument interpretation](https://github.com/advisories/GHSA-r825-w8mm-5pxw)
and [Windows path validation](https://github.com/advisories/GHSA-587h-7wmj-h5pm).
The selected Vite 8.3.4 patch is beyond their affected range and supports Node 24.

## Safety and scope self-review

- The broker boundary still requires a verified single paper-account context and
  connects only to the fixed loopback paper endpoint. No live path was added.
- Session scheduling retains server checks at authorization, reservation and
  dispatch. Restart disarms entries. Regular hours remain the strategy default;
  extended hours require supervision and explicit stop-limit protection.
- Quote-only diagnostics retain risk reservation, explicit one-shot authorization,
  durable order identity and uncertain-outcome handling. Diagnostic results do
  not satisfy ordinary strategy execution qualification.
- Protection reconciliation checks the owned quantity, broker identity, order
  type, session flag and protective limit. Run removal preserves audit history,
  waits for terminal evidence and released capacity, and exposes late fills.
- Structured diagnostics omit raw broker messages, exception arguments and
  locals. The existing secret scan remains required for publication.
- No outstanding P0/P1 finding was identified in this self-review. Real Gateway
  compatibility and protective execution remain operator evidence requirements.

## Verification

Installation and checks use Python 3.12.10 in the ignored isolated environment
`.tmp/dependency-remediation-venv`. Its installed versions are AnyIO 4.14.2 and
Certifi 2026.10.19. The shared interpreter was separately checked and remains at
AnyIO 4.14.1 and Certifi 2026.6.17.

Commands from the repository root, with the isolated environment first on PATH:

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pip check
python -m pip_audit --disable-pip --no-deps -r backend/requirements-lock.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend audit --audit-level=low
.\scripts\verify.ps1
git diff --check
```

Installation succeeded; `pip check` reported `No broken requirements found.`
The early Python audit reported `No known vulnerabilities found`.
After the additional frontend patches, npm ci installed 208 packages and audited
209 packages successfully. Its audit and the separate unchanged-threshold
`npm.cmd --prefix frontend audit --audit-level=low` both reported zero
vulnerabilities. A complete gate rerun covers the final dependency set.

The final `scripts/verify.ps1` rerun passed at 2026-10-21 14:40 Sydney time:

- 857 backend tests passed, including deterministic replay, risk, OMS, broker
  doubles, protection, session boundaries and crash/recovery cases.
- 188 frontend tests passed; formatting, lint, types and production build passed.
- The browser walkthrough passed, including accessibility, layout and existing
  Windows visual-baseline comparisons without updates.
- Secret scanning found no recognized credential patterns. The Python audit
  reported no known vulnerabilities; npm reported zero vulnerabilities at the
  unchanged low-severity threshold. The full command reached `verify: ok`.
- `git diff --check` passed. The ordinary gate generated the verification record;
  its fingerprint was checked against the current source/build and it explicitly
  retains `paper_trials: false`.

Verified source/build fingerprint:
`2e62eef17b222a187b1ddc7776d951ac08b286601d22fcf2f0d61db25fd757be`.

Nonblocking notices remain: the upstream HTTPX TestClient deprecation, production
bundle-size advisory, recommendation to hash Python requirement artifacts, and
the browser harness's color-environment notice. No audit exclusion or check was
added to suppress these or the vulnerabilities.

Publication also requires successful Windows and Ubuntu CI for the pushed commit.
Remote results are reported with the final commit and Actions links; they are not
inferred from this local verification record.

## Operating service and remaining acceptance

This task does not upgrade the shared runtime, restart the application, connect
Gateway, submit a broker order or send a notification. Before later paper trials,
the operator must disarm and reconcile, stop the service, install the updated
requirements into the intended runtime, then restart and reconcile before fresh
arming. The temporary verification environment is not a service deployment.

Supervised acknowledgement/cancellation, normal strategy fill/protection/close,
extended-session protection, recovery and five-session release acceptance remain
separate requirements in the [operator guide](PAPER_OPERATOR_GUIDE.md).
Automated verification records retain `paper_trials: false`.
