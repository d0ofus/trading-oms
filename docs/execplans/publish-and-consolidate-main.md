# ExecPlan: Publish the integration and consolidate on main

## 1. Goal

Publish the verified typed strategy integration to GitHub and retain one active working copy at
`C:/Users/ErvinLieu/Documents/Projects/trading-oms`, with only the `main` branch locally and on
GitHub. The user explicitly requested the merge and consolidation on 2026-09-15.

## 2. Non-goals

No new trading behavior, deployment, broker connection, data migration, or additional development
slice. Historical branch tips are preserved as backups rather than merged into the application.

## 3. Safety constraints

Keep simulation-only execution and all verified safety controls. Preserve the entire original
working folder, including ignored runtime evidence, before replacing it. Preserve all remote
branch tips before deletion. Do not force-update main, rewrite published history, expose secrets,
or change repository protection settings. Backups remain local and outside the active repository.

## 4. Current state

GitHub main is `0d1224b275ed52a4c1df0c48fc6f66a83b9311d1`; the clean integration checkout contains
`dae7e93d92194a15bbe8c2382b2944abc0bc9048`. Verification passed 767 backend and 188 frontend
tests. Browser checks remain unavailable. There are 29 older remote feature branches and old
open PR #7. Some old tips are not main ancestors, so their objects must be archived explicitly.
The original folder has experimental uncommitted work and an unhealthy Git object store; its
265 source files still match the prior source-backup manifest.

## 5. Proposed design

Create and verify a complete local archive of the original directory and a Git bundle of all
healthy integration/remote refs. Publish an integration PR, wait for its actual head checks, and
merge it after verifying its head and base. Sync a local main to the resulting remote main.
Delete the archived feature refs after checking that their remote tips have not changed. Close
the superseded old PR as part of the requested branch cleanup. Preserve the canonical directory
itself, replace its backed-up contents with the healthy main checkout, and remove the empty
integration directory. The original experimental runtime state stays in the archive; no implicit
migration into the integrated application is attempted.

## 6. Data model changes

None. Existing state is preserved in the complete backup archive.

## 7. API changes

None. Repository operations use existing authenticated Git/GitHub access.

## 8. Test plan

Verify archive contents and SHA-256 manifest, Git bundle integrity, unchanged remote tips, PR
checks and merge result. After consolidation, run the complete repository gate from the canonical
directory and confirm a clean working tree, one local/remote branch, healthy Git objects, and an
exact HEAD match with GitHub main.

## 9. Verification commands

```powershell
git bundle verify <local-backup>/all-branches.bundle
git diff --check
.\scripts\verify.ps1
npm.cmd --prefix frontend run build
git fsck --connectivity-only
git status --short --branch
git ls-remote --heads origin
```

## 10. Rollback plan

Restore the original files from the verified complete archive if local consolidation fails.
Recover deleted branch refs from the Git bundle. A rollback of published application code would
be a normal revert commit, not a forced update of main. Do not replay old experimental state.

## 11. Implementation steps

1. Inspect local/remote state and confirm merge authorization. Done.
2. Preserve and verify the original folder and all Git refs.
3. Publish the integration PR, check its exact head, and merge after green CI.
4. Sync main and remove archived feature branches and the superseded old PR.
5. Consolidate the healthy checkout into the canonical project folder.
6. Run final verification and report the final SHA, sole branch, path and backups.

## 12. Completion criteria

The integrated content is on GitHub main. The canonical directory is the sole active working copy,
has a clean working tree and healthy Git object store, and matches origin/main exactly. Only main
remains among local and remote branch heads. Full verification passes. Original files and all
historical branch tips remain recoverable from verified local backups.

## 13. Risks and assumptions

The latest user instruction supersedes the earlier integration plan's no-push/no-merge scope.
Git still requires a branch name; "without any branches" means one main branch and no feature
branches. Deleting old branch refs does not remove their archived history. Backup archives are
recovery artifacts, not additional active working copies. Browser visual verification remains
an explicitly recorded limitation; the user has authorized publication with that limitation known.
