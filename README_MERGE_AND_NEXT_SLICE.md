# Merge and next-slice add-on

Copy these files into the repo root:

```text
.codex/prompts/11-human-gated-slice-conveyor.md
.codex/prompts/12-merge-current-pr-and-run-next-recommended-slice.md
docs/CODEX_MERGE_AND_NEXT_SLICE.md
```

Then commit them.

## PowerShell install example

```powershell
cd C:\Users\ErvinLieu\Documents\Projects\trading-oms
robocopy "$env:USERPROFILE\Downloads\codex-merge-next-slice-pack" . /E
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
git add .codex/prompts/11-human-gated-slice-conveyor.md .codex/prompts/12-merge-current-pr-and-run-next-recommended-slice.md docs/CODEX_MERGE_AND_NEXT_SLICE.md README_MERGE_AND_NEXT_SLICE.md
git commit -m "Add Codex merge and next-slice workflow"
git push
```

## Use

After Codex pushes a slice branch, it should now recommend the next slice automatically.

To let Codex merge and run the next recommended slice after your review, type:

```text
APPROVE MERGE CURRENT PR AND RUN NEXT RECOMMENDED SLICE
```

Codex must stop if GitHub CLI is unavailable, authentication fails, CI is not green, or the next slice is ambiguous.
