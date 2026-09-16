"""Record and check the exact source fingerprint covered by the local development gate."""

import hashlib
import json
from pathlib import Path

from .store import now

ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / ".tmp" / "paper-verification.json"


def fingerprint():
    paths = []
    for directory in (
        "backend/src",
        "backend/tests",
        "frontend/src",
        "frontend/e2e",
        "frontend/dist",
        "scripts",
    ):
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and p.suffix in {".py", ".tsx", ".ts", ".css", ".ps1", ".js", ".html"}
        )
    paths += [
        ROOT / name
        for name in (
            "backend/pyproject.toml",
            "backend/requirements-lock.txt",
            "frontend/package-lock.json",
            "frontend/playwright.config.ts",
            "frontend/vite.config.ts",
            "scripts/verify.ps1",
        )
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verified():
    try:
        record = json.loads(GATE.read_text(encoding="utf-8"))
        return record["passed"] is True and record["fingerprint"] == fingerprint()
    except (OSError, ValueError, KeyError):
        return False


if __name__ == "__main__":
    GATE.parent.mkdir(exist_ok=True)
    GATE.write_text(
        json.dumps(
            {
                "passed": True,
                "fingerprint": fingerprint(),
                "timestamp": now(),
                "scope": "automated_offline_gate",
                "paper_trials": False,
            }
        ),
        encoding="utf-8",
    )
