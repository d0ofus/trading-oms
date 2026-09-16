import zipfile

import pytest

from trading_oms_backend.workspace.recovery import backup_bundle, restore_bundle, validate_bundle
from trading_oms_backend.workspace.store import Conflict, Store


def test_backup_restores_capture_integrity_and_disarms_into_new_directory(tmp_path):
    store = Store(tmp_path / "paper")
    capture = store.capture([{"price": "100", "timestamp": "fixture"}])
    packed = store.capture_batch([{"price": "101", "sequence": 1}])
    store.put("run", "run", {"id": "run", "armed": True})
    store.event("strategy.signal", {"capture": capture})
    bundle = backup_bundle(store, tmp_path / "backups")
    result = restore_bundle(bundle, tmp_path / "recovery")
    restored = Store(tmp_path / "recovery")
    assert result["integrity"] == "ok"
    assert restored.emergency()
    assert restored.get("run", "run")["armed"] is False
    assert restored.load_capture(packed) == [{"price": "101", "sequence": 1}]
    assert (restored.directory / "captures" / f"{capture}.json").read_bytes() == (
        store.directory / "captures" / f"{capture}.json"
    ).read_bytes()
    with pytest.raises(Conflict, match="existing state"):
        restore_bundle(bundle, store.directory)


def test_modified_capture_cannot_pass_backup_restore(tmp_path):
    store = Store(tmp_path / "paper")
    store.capture([{"price": "100"}])
    bundle = backup_bundle(store, tmp_path / "backups")
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("unexpected.txt", "tampered")
    with pytest.raises(Conflict):
        validate_bundle(bundle)
