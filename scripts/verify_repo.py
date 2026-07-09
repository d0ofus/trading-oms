from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "AGENTS.md",
    "PLANS.md",
    "README.md",
    "GETTING_STARTED_WINDOWS.md",
    "FIRST_CODEX_LOOP.md",
    ".codex/config.toml",
    ".codex/prompts/00-repo-inspection.md",
    ".codex/prompts/01-plan-only.md",
    ".codex/prompts/02-implement-approved-plan.md",
    ".codex/prompts/03-self-review.md",
    ".codex/prompts/04-red-team-trading-safety.md",
    ".codex/prompts/05-fix-review-findings.md",
    ".codex/prompts/06-next-slice-plan.md",
    "docs/CODEX_OPERATING_GUIDE.md",
    "docs/ROADMAP.md",
    "docs/SECURITY_BASELINE.md",
    "docs/LIVE_TRADING_READINESS_CHECKLIST.md",
    ".github/workflows/ci.yml",
    ".github/pull_request_template.md",
    ".env.example",
    ".gitignore",
    "Makefile",
    "scripts/verify.ps1",
    "scripts/verify_repo.py",
]

FORBIDDEN_FILES = [
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
]

REQUIRED_TEXT = {
    "AGENTS.md": [
        "Do not enable live trading",
        "Default mode must be paper or simulation",
        "Every order must pass the risk engine",
    ],
    ".env.example": [
        "APP_MODE=paper",
        "LIVE_TRADING_ENABLED=false",
        "IBKR_ACCOUNT_MODE=paper",
    ],
    ".codex/config.toml": [
        'approval_policy = "never"',
        'sandbox_mode = "workspace-write"',
        'model_reasoning_effort = "xhigh"',
        'plan_mode_reasoning_effort = "xhigh"',
        "network_access = true",
    ],
}

FORBIDDEN_TEXT = [
    "LIVE_TRADING_ENABLED=true",
    "APP_MODE=live",
    "IBKR_ACCOUNT_MODE=live",
]

SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".tmp",
}


def fail(message: str) -> None:
    print(f"verify_repo.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _should_skip_path(path: Path) -> bool:
    try:
        relative_parts = path.relative_to(ROOT).parts
    except ValueError:
        relative_parts = path.parts
    return any(part in SKIPPED_DIRECTORY_NAMES for part in relative_parts)


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        fail("Missing required files:\n  " + "\n  ".join(missing))

    present_forbidden = [path for path in FORBIDDEN_FILES if (ROOT / path).exists()]
    if present_forbidden:
        fail(
            "Forbidden local/secret files present:\n  " + "\n  ".join(present_forbidden)
        )

    for rel, needles in REQUIRED_TEXT.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                fail(f"{rel} is missing required text: {needle}")

    scan_exts = {".md", ".toml", ".example", ".yml", ".yaml", ".py", ".ps1", ""}
    for path in ROOT.rglob("*"):
        if _should_skip_path(path):
            continue
        if not path.is_file() or path.suffix not in scan_exts:
            continue
        if path.relative_to(ROOT).as_posix() == "scripts/verify_repo.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for forbidden in FORBIDDEN_TEXT:
            if forbidden in text:
                fail(f"Forbidden text found in {path.relative_to(ROOT)}: {forbidden}")

    print("verify_repo.py: ok")


if __name__ == "__main__":
    main()
