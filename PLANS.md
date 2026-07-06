# PLANS.md

This file defines the ExecPlan standard for complex, architectural, or safety-critical work.

Codex must create an ExecPlan before implementation when a task affects:

- trading behavior;
- risk checks;
- order state;
- broker integration;
- market-data handling;
- event journaling;
- approval flow;
- credentials or configuration;
- production deployment;
- data model migrations;
- security controls;
- CI or verification gates.

## ExecPlan template

Use this exact structure.

```markdown
# ExecPlan: <short title>

## 1. Goal

Describe the user-visible outcome.

## 2. Non-goals

List what is intentionally out of scope.

## 3. Safety constraints

List all relevant safety constraints, especially:
- no live trading;
- no secrets;
- default paper/simulation mode;
- stale data behavior;
- risk checks;
- audit logging;
- approval requirements.

## 4. Current state

Summarize the relevant existing files and behavior.

## 5. Proposed design

Describe the implementation approach.

## 6. Data model changes

Describe new tables, records, schemas, or state transitions.
If none, write `None`.

## 7. API changes

Describe new endpoints, CLI commands, config keys, or public interfaces.
If none, write `None`.

## 8. Test plan

List unit, integration, replay, chaos, and e2e tests as applicable.

## 9. Verification commands

List exact commands to run, including `make verify` or `./scripts/verify.ps1`.

## 10. Rollback plan

Describe how to revert safely.

## 11. Implementation steps

Use small ordered steps.

## 12. Completion criteria

List objective acceptance criteria.

## 13. Risks and assumptions

List known risks, assumptions, and unresolved decisions.
```

## Planning rules

- Keep plans specific.
- Do not hide major design choices.
- Do not implement while asked to plan only.
- For safety-critical slices, prefer smaller scope.
- If requirements conflict, stop and explain the conflict.
- If a task asks for live trading, refuse that part and propose a paper/simulation-safe alternative.

## Implementation rules after plan approval

After the user approves an ExecPlan, Codex should:

1. restate the approved scope;
2. add or update tests first where practical;
3. implement in small logical chunks;
4. run verification;
5. fix failures;
6. self-review;
7. update docs;
8. summarize evidence.
