# Getting Started on Windows

This guide assumes your repo is named `trading-oms` and your GitHub username is `d0ofus`.

## 1. Clone the repo

Because SSH failed with `Permission denied (publickey)`, use HTTPS first:

```powershell
cd C:\Users\ErvinLieu\Documents\Projects
git clone https://github.com/d0ofus/trading-oms.git
cd trading-oms
```

If the folder already exists, use:

```powershell
cd C:\Users\ErvinLieu\Documents\Projects\trading-oms
git status
```

## 2. Apply the starter files

Extract `trading-oms-starter.zip` somewhere, for example your Downloads folder.

Then copy the extracted files into the repo root. `robocopy` copies dot-directories such as `.codex` and `.github` reliably.

```powershell
cd C:\Users\ErvinLieu\Documents\Projects\trading-oms
robocopy "$env:USERPROFILE\Downloads\trading-oms-starter" . /E
```

Robocopy may return exit code `1` even when successful. That usually means files were copied.

## 3. Verify the scaffold

```powershell
.\scripts\verify.ps1
```

If you have `make` installed, also run:

```powershell
make verify
```

## 4. Commit the scaffold

```powershell
git status
git add .
git commit -m "Add repo operating system and Codex guidance"
git push
```

If this is a new branch:

```powershell
git push -u origin HEAD
```

## 5. Open in VS Code

```powershell
code .
```

Install or open the Codex extension/app, select this repo, and keep permissions conservative:

- sandbox: workspace-write;
- approval policy: on-request;
- command network access: off unless explicitly approved.

## 6. First Codex check

Paste this into Codex:

```text
Read AGENTS.md, PLANS.md, docs/CODEX_OPERATING_GUIDE.md, and docs/ROADMAP.md.

Do not edit files.

Summarize:
1. the project purpose;
2. the non-negotiable safety rules;
3. the standard implementation loop;
4. the current repo state;
5. the next recommended safe slice;
6. any setup problems you notice.
```

## 7. Start the first implementation loop: Slice 002 plan

Create a branch:

```powershell
git switch -c slice-002-backend-frontend-skeleton
```

Then paste the Slice 002 plan prompt from `FIRST_CODEX_LOOP.md`.

Do not let Codex implement until it has produced a plan you have reviewed.
