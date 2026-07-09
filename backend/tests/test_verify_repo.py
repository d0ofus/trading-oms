from __future__ import annotations

import importlib.util
from pathlib import Path


def test_verify_repo_skips_generated_tmp_directories() -> None:
    module = _load_verify_repo_module()

    assert module._should_skip_path(module.ROOT / ".tmp")
    assert module._should_skip_path(module.ROOT / ".tmp" / "slice047-work" / "scripts")
    assert not module._should_skip_path(module.ROOT / "backend" / "src" / "example.py")


def _load_verify_repo_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "verify_repo.py"
    spec = importlib.util.spec_from_file_location("verify_repo_for_test", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
