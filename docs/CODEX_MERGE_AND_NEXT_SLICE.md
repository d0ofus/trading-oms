# Codex merge-and-next-slice workflow

## Goal

Reduce repetitive prompts while keeping a human approval gate.

The streamlined flow is:

```text
Codex implements one slice
→ Codex stops at READY FOR HUMAN REVIEW
→ human reviews
→ human says APPROVE COMMIT AND PUSH
→ Codex commits/pushes
→ Codex recommends the next slice automatically
→ human either merges manually or says APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
→ Codex performs mechanical merge checks and runs exactly one next slice
```

## Recommended safe path

The safest path is still manual merge:

```text
PR MERGED. APPROVE NEXT SLICE AND RUN: <auto-filled slice id/title>
```

This keeps the GitHub merge button as a hard human gate.

## Optional one-command path

After reviewing the PR and ensuring CI is green, the human may type:

```text
APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
```

This lets Codex:

1. verify the current branch and PR;
2. verify checks are green;
3. squash-merge the PR using GitHub CLI;
4. sync local main;
5. identify the next slice from `docs/SLICES.md`;
6. mark exactly one slice approved;
7. run that one slice;
8. stop at human review.

## Requirements for Codex-assisted merge

This requires:

- GitHub CLI installed;
- `gh auth status` succeeds;
- Codex command network access is available;
- PR exists for the current branch;
- checks are passing;
- PR is mergeable;
- branch head SHA matches the PR head SHA.

## Safety rules

Codex must stop if:

- current branch is `main`;
- working tree is dirty;
- PR checks fail or are pending;
- PR is not mergeable;
- PR head SHA does not match local HEAD;
- next slice is ambiguous;
- next slice is unsafe;
- any verification command fails.

## Why the next slice should be automatic

The human should not need to remember slice numbers. Codex should use `docs/SLICES.md` as the source of truth and output exact copy/paste approval text.

Example:

```text
Recommended next slice:
Slice 004 — append-only event journal

Reply with:

PR MERGED. APPROVE NEXT SLICE AND RUN: Slice 004 — append-only event journal

or:

APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
```
