# Codex Human-Gated Continuation

This project can use a semi-autonomous Codex loop:

```text
Codex runs one approved slice
→ Codex verifies, repairs, self-reviews, and red-teams
→ Codex asks the human to review
→ human approves commit/push or requests changes
→ Codex pushes the branch
→ Codex asks whether to start the next slice
→ human approves the next slice
→ Codex starts the next slice
```

The human should not need to remember separate prompt filenames after the loop starts. Codex should present the next valid choices at each gate.

## Safety boundary

Codex must not start the next slice merely because it finished the previous one. The human must explicitly approve the next slice.

## Recommended first command in Codex

```text
Read `.codex/prompts/11-human-gated-slice-conveyor.md` and execute it exactly.
```

## Human replies used by the protocol

After Codex finishes implementing a slice:

```text
APPROVE COMMIT AND PUSH
```

or:

```text
REQUEST CHANGES: <specific changes>
```

or:

```text
STOP
```

After Codex pushes the branch and you merge the PR to main:

```text
PR MERGED. APPROVE NEXT SLICE AND RUN: <next slice id and title>
```

If you knowingly want to create a stacked branch before merging the PR:

```text
STACKED BRANCH APPROVED. APPROVE NEXT SLICE AND RUN: <next slice id and title>
```

## Recommendation

For this trading platform, prefer PR merge and CI pass before starting the next slice from `main`. Stacked branches can be useful but make review harder.
