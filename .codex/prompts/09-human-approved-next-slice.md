The human has approved moving to the next slice.

Read:
- `AGENTS.md`
- `PLANS.md`
- `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
- `docs/SLICES.md`
- `docs/ROADMAP.md`

Do not implement yet.

Task:
1. Mark the completed slice as `complete` in `docs/SLICES.md` only if it was already committed or the human explicitly confirms it is accepted.
2. Select the next safe slice from `docs/SLICES.md` and `docs/ROADMAP.md`.
3. Mark exactly one next slice as `approved_for_autonomous_run`.
4. Ensure no other slice is marked `approved_for_autonomous_run`.
5. Return the selected slice, branch name, goal, non-goals, and acceptance criteria.
6. Ask the human to approve running `.codex/prompts/07-run-one-approved-slice-autonomously.md`.

Do not implement the next slice in this prompt.
