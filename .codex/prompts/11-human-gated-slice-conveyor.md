# Prompt 11 — Human-gated slice conveyor

## Purpose

Run a safe one-slice-at-a-time Codex workflow.

Codex may work autonomously inside a human-approved slice, but must stop at explicit gates before:

- committing;
- pushing;
- merging;
- starting another slice;
- adding network access;
- adding dependencies;
- changing safety rules;
- broker integration;
- IBKR integration;
- live trading.

## Operating rule

Codex must always leave the human with exact copy/paste choices.

Do not ask the human to invent the next slice ID or title. Recommend the next slice automatically from `docs/SLICES.md` and include the exact approval phrase.

## Start command

The human may start this conveyor with:

```text
Read `.codex/prompts/11-human-gated-slice-conveyor.md` and execute it exactly.
```

## Initial procedure

1. Read:
   - `AGENTS.md`
   - `PLANS.md`
   - `docs/CODEX_OPERATING_GUIDE.md`
   - `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
   - `docs/SLICES.md`
   - `docs/ROADMAP.md`

2. Identify the one slice marked:

```text
approved_for_autonomous_run
```

3. If exactly one approved slice exists, run exactly that slice using:

```text
.codex/prompts/07-run-one-approved-slice-autonomously.md
```

4. If no approved slice exists, recommend the next slice from `docs/SLICES.md` and stop with an exact approval phrase.

5. If more than one approved slice exists, stop and ask the human to approve exactly one.

## After implementation gate

When a slice implementation is complete, Codex must stop with:

```text
READY FOR HUMAN REVIEW
```

Include:

- slice ID/title;
- branch;
- files changed;
- verification commands run;
- verification result;
- self-review findings;
- red-team safety findings;
- any risks or deferred items;
- recommended next slice from `docs/SLICES.md`.

Then include this exact copy/paste block:

```text
After reviewing the diff, reply with one of:

APPROVE COMMIT AND PUSH
REQUEST CHANGES: <specific changes>
STOP
```

## After commit/push gate

If the human replies:

```text
APPROVE COMMIT AND PUSH
```

Codex may:

1. rerun verification;
2. commit the current slice if not already committed;
3. push the current branch.

Codex must then stop with:

```text
PUSH COMPLETE — NEXT SLICE GATE
```

Codex must automatically identify the recommended next slice from `docs/SLICES.md` and include the exact command block below.

Use this format:

```text
Recommended next slice:
<Slice ID> — <Slice title>

Reason:
<one sentence based on docs/SLICES.md and docs/ROADMAP.md>

Safest path:
Open/review the PR, wait for CI, merge to main in GitHub, then reply:

PR MERGED. APPROVE NEXT SLICE AND RUN: <Slice ID> — <Slice title>

One-command Codex-assisted path:
If you have reviewed the PR and want Codex to perform the mechanical merge and then run the next recommended slice, reply:

APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE

Other options:
REQUEST CHANGES: <specific changes>
STOP
```

Do not ask the human to type the slice ID/title manually unless the next slice is ambiguous.

## If the human says PR merged

If the human replies with:

```text
PR MERGED. APPROVE NEXT SLICE AND RUN: <Slice ID> — <Slice title>
```

Codex must:

1. sync local `main`;
2. verify the named slice is the next valid slice in `docs/SLICES.md`;
3. mark exactly that slice as `approved_for_autonomous_run`;
4. create/switch to its slice branch;
5. run exactly one autonomous slice;
6. stop again at `READY FOR HUMAN REVIEW`.

## If the human approves merge and next recommended slice

If the human replies with:

```text
APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
```

Codex must read and execute:

```text
.codex/prompts/12-merge-current-pr-and-run-next-recommended-slice.md
```

This is a combined human approval for:

```text
merge current reviewed PR
→ sync main
→ select the next recommended slice from docs/SLICES.md
→ run exactly one next slice
→ stop at READY FOR HUMAN REVIEW
```

Codex must not start more than one next slice.

## Forbidden behavior

Codex must not:

- silently merge;
- silently approve a next slice;
- select multiple next slices;
- start the next slice before a human approval phrase;
- bypass failing checks;
- bypass requested changes;
- enable live trading;
- add broker credentials;
- expose secrets;
- alter GitHub branch protection;
- force-push;
- merge unrelated PRs.
