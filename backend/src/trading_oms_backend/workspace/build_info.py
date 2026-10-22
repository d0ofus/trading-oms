"""Small startup identities: no source traversal on periodic status reads."""

import hashlib
import re
from pathlib import Path

from .store import now


def build_identity(frontend=None):
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    asset = None
    if frontend and (frontend / "index.html").exists():
        match = re.search(r'src="/assets/([^"/]+\.js)"', (frontend / "index.html").read_text())
        asset = match[1] if match else None
    return {"backend": digest.hexdigest()[:16], "frontend": asset, "started_at": now()}
