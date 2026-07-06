The human has reviewed the autonomous slice result and approves a local commit.

Read:
- `AGENTS.md`
- `docs/CODEX_SLICE_AUTONOMY_PROTOCOL.md`
- `docs/SLICES.md`

Before committing:
1. Run `git status`.
2. Run final verification:
   - `make verify` if available;
   - otherwise `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1`.
3. Confirm no secrets are present in the diff.
4. Confirm no live-trading path is present.
5. Commit the slice using a concise message.

Do not push unless the human explicitly says `APPROVE PUSH`.

Return:
- commit hash;
- verification result;
- files committed;
- any remaining risks.
