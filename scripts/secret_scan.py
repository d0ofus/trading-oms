"""Scan reviewable repository files without printing candidate secret values."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub credential": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b"),
    "OpenAI credential": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b"),
    "broker account identifier": re.compile(r"\bDU[1-9][0-9]{5,}\b"),
    "Telegram credential": re.compile(r"\b[1-9][0-9]{5,14}:[A-Za-z0-9_-]{30,}\b"),
    "Healthchecks credential": re.compile(r"https://hc-ping\.com/(?!00000000)[a-f0-9]{8}-[a-f0-9-]{27}\b"),
}


def main():
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT).decode().split("\0")
    findings = []
    for name in names:
        path = ROOT / name
        if not name or not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".ico", ".zip"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeError:
            continue
        for line_number, line in enumerate(lines, 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{name}:{line_number}: potential {label} (value withheld)")
    if findings:
        print("\n".join(findings))
        raise SystemExit(1)
    print("Secret scan: no recognized credential patterns in reviewable files.")


if __name__ == "__main__":
    main()
