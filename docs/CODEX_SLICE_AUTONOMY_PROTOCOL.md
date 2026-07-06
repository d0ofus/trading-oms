# Codex Slice Autonomy Protocol

## Purpose

This protocol lets Codex run an autonomous implementation loop for exactly one approved slice at a time.

The goal is to reduce manual prompting while preserving safety gates for a trading system.

## Core rule

Codex may autonomously plan, implement, test, repair, self-review, and prepare a branch for one approved slice.

Codex must not auto-advance to the next slice.

After each slice, Codex must stop and return a `READY FOR HUMAN REVIEW` report.

## Why one slice at a time

This repository is for safety-critical trading software. Autonomous work is useful for implementation mechanics, but humans must approve scope changes, slice boundaries, safety assumptions, and next-slice progression.

## Allowed autonomous actions within one approved slice

Codex may:

1. read repo guidance and docs;
2. inspect the current repository state;
3. create or switch to the slice branch;
4. create an ExecPlan if the slice is complex or safety-critical;
5. add or update tests where practical;
6. implement the approved scope;
7. run verification commands;
8. perform up to three focused repair cycles;
9. self-review the diff;
10. red-team trading safety implications;
11. fix P0 and P1 findings;
12. update docs if setup or behavior changes;
13. stage a final summary for human review.

## Disallowed autonomous actions

Codex must not:

1. implement live trading;
2. add real credentials or secrets;
3. create live broker order-transmission paths;
4. connect to IBKR unless the approved slice explicitly permits paper-only adapter work;
5. auto-advance to the next slice;
6. merge to `main`;
7. push to a remote repository without human approval;
8. weaken safety checks to make tests pass;
9. delete audit or safety requirements;
10. skip verification because it is inconvenient.

## Repair loop

Codex should use this loop inside a slice:

```text
inspect
→ plan
→ tests first where practical
→ implement
→ verify
→ repair failures
→ verify again
→ self-review
→ red-team safety review
→ fix P0/P1
→ final verify
→ stop for human review
```

Maximum focused repair cycles before stopping: 3.

If the slice still fails after 3 repair cycles, Codex must stop and report:

- the failing command;
- the failing output summary;
- likely root cause;
- files touched;
- safest next action.

## Human review gate

At the end of each slice, the human should review:

```bash
git status
git diff --stat
git diff
make verify
```

On Windows without `make`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

The human may then approve one of these actions:

```text
APPROVE COMMIT
APPROVE PUSH
APPROVE NEXT SLICE
REQUEST FIXES
ABANDON SLICE
```

## Final report format

Codex must end each autonomous slice with this structure:

```markdown
# READY FOR HUMAN REVIEW

## Slice

<slice id and title>

## Goal result

<met / partially met / blocked>

## Files changed

<list>

## Checks run

<commands and results>

## Acceptance criteria status

- [x] criterion 1
- [ ] criterion 2, with reason

## Safety review

- Live trading path added: yes/no
- Secrets added: yes/no
- Broker connectivity added: yes/no
- Risk/OMS implications: summary

## Self-review findings

P0: ...
P1: ...
P2: ...

## Recommended human commands

```bash
git status
git diff --stat
make verify
```

## Next recommendation

<approve commit / request fixes / next slice suggestion>
```
