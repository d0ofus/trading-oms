Read `AGENTS.md`, `PLANS.md`, and the approved ExecPlan.

Implement only the approved scope.

Process:
1. Restate the approved scope briefly.
2. Add or update tests first where practical.
3. Implement in the smallest safe slice.
4. Run `make verify`; on Windows, also use `.\scripts\verify.ps1` if `make` is unavailable.
5. Fix failures for up to three focused repair cycles.
6. Self-review.
7. Fix P0/P1 findings.
8. Update docs.
9. Summarize changed files, commands run, verification result, safety implications, and next recommended slice.

Do not add live trading, real credentials, market data, broker order transmission, or IBKR integration unless the approved plan explicitly covers a paper/simulation-safe adapter design.
