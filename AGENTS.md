# AGENTS.md

## Project identity

This repository is for a production-oriented, self-hosted, semi-automated trading workflow and order-management platform.

Long-term goal: a safety-first trading operations system that can eventually connect to Interactive Brokers through TWS or IB Gateway.

Near-term goal: deterministic simulation, fake broker execution, event journaling, replay, risk checks, manual approval tickets, and auditability.

This is safety-critical software. Treat all trading-related changes as high-risk until proven otherwise.

## Non-negotiable trading safety rules

These rules override all other instructions.

1. Do not enable live trading.
2. Do not create any code path that can transmit a live order.
3. Do not add real broker credentials.
4. Do not add real Telegram tokens.
5. Do not add OpenAI keys, GitHub tokens, account IDs, passwords, certificates, private keys, or secrets.
6. Default mode must be paper or simulation.
7. Broker-specific code must be isolated behind an adapter interface.
8. Interactive Brokers integration, when introduced, must be paper-only at first.
9. Live trading must remain disabled by default and gated by an explicit readiness checklist.
10. Every signal, risk decision, approval decision, order intent, order transition, fill, cancel, reject, reconnect, reconciliation event, and emergency event must be journaled.
11. Every order must pass the risk engine before approval or submission.
12. Semi-automatic human approval must exist before automatic execution.
13. Duplicate orders must be prevented.
14. Stale market data must block trading decisions.
15. Unknown broker state must block new risk-increasing decisions.
16. Disconnect, reconnect, and reconciliation behavior are core functionality.
17. IBKR TWS or Gateway API ports must never be exposed to the public internet.
18. Any risk-increasing entry order must have a protective-order plan or an explicitly approved exception.
19. A position without expected protection must raise a critical alert.
20. No secrets may appear in repo files, logs, docs, tests, screenshots, or alert payloads.

## Architecture build order

Build in this order. Do not skip to IBKR or the visual builder early.

1. Repository guidance and verification gate.
2. Backend/frontend skeleton with real checks.
3. Safe configuration system.
4. Append-only event journal.
5. Deterministic market-data replay.
6. Bar builder.
7. First simple replay-only strategy.
8. Risk engine.
9. Fake broker.
10. OMS state machine.
11. Approval tickets.
12. Alerts.
13. UI shell.
14. Strategy DSL.
15. Visual workflow builder.
16. IBKR paper adapter.
17. Reconnect/reconciliation/chaos tests.
18. Live-trading readiness checklist.
19. Controlled production rollout only after explicit human approval.

## Standard Codex workflow

For any non-trivial task, Codex must follow this loop:

1. Read `AGENTS.md`, `PLANS.md`, and relevant docs.
2. State a short plan.
3. Update or add tests first where practical.
4. Implement the smallest useful slice.
5. Run verification.
6. Fix failures.
7. Self-review for safety, correctness, maintainability, and scope creep.
8. Fix P0/P1 review findings.
9. Update docs when behavior or setup changes.
10. Summarize changed files, commands run, results, risks, and next slice.

For complex or safety-critical work, Codex must create an ExecPlan using `PLANS.md` before editing implementation files.

## Required verification commands

At minimum, run one of these from the repository root:

```bash
make verify
```

On Windows without `make`:

```powershell
.\scripts\verify.ps1
```

As the repo matures, `make verify` must run real checks: formatting, linting, type checks, tests, replay tests, security checks, and eventually chaos tests.

## Definition of done

A task is not complete until:

1. The requested scope is implemented.
2. Scope was not broadened without approval.
3. Tests were added or updated where practical.
4. Verification passes, or any failure is clearly explained with exact command output.
5. No secrets were introduced.
6. No live-trading path was introduced.
7. Safety-sensitive behavior is documented.
8. Docs were updated when setup, commands, architecture, or behavior changed.
9. Final summary includes evidence of checks run.

## Review priorities

Review in this order:

1. Trading safety.
2. Secret leakage.
3. Live-order prevention.
4. Risk and OMS correctness.
5. Determinism and auditability.
6. Test coverage.
7. Simplicity.
8. Maintainability.
9. Developer experience.
10. Performance.

## Coding principles

- Prefer small vertical slices.
- Prefer explicit state machines over implicit state.
- Prefer typed models and validation.
- Prefer deterministic tests.
- Prefer append-only audit records for critical trading events.
- Avoid hidden global state.
- Avoid broker-specific assumptions in core domain code.
- Keep adapters thin and replaceable.
- Make unsafe states unrepresentable where practical.
