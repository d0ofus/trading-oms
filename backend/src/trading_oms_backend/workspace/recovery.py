from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path

from .graph import canonical
from .store import Conflict, Connection, Store, now


def backup_bundle(store: Store, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    identity = uuid.uuid4().hex
    temporary = directory / f"backup-{identity}.pending"
    final = directory / f"paper-{now()[:10]}-{identity[:8]}.zip"
    manifest = {"schema": 1, "environment": "paper", "created_at": now(), "files": {}}
    with tempfile.TemporaryDirectory(prefix="oms-backup-") as staging:
        database = store.backup(Path(staging))
        files = [(database, "workspace.sqlite3", database.stat().st_size)]
        files.extend(
            (path, "captures/" + path.name, path.stat().st_size)
            for path in (store.directory / "captures").glob("*.json")
        )
        with sqlite3.connect(database, factory=Connection) as db:
            packs = db.execute(
                "SELECT file, MAX(offset+length) FROM captures GROUP BY file"
            ).fetchall()
        for filename, length in packs:
            if not re.fullmatch(r"trades-\d{4}-\d{2}-\d{2}\.jsonl", filename):
                raise Conflict("Invalid capture pack path.")
            files.append((store.directory / "captures" / filename, "captures/" + filename, length))
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, name, length in files:
                checksum = hashlib.sha256()
                remaining = length
                with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as target:
                    while remaining:
                        chunk = source.read(min(512 * 1024, remaining))
                        if not chunk:
                            raise Conflict(
                                "A capture ended before its committed manifest boundary."
                            )
                        target.write(chunk)
                        checksum.update(chunk)
                        remaining -= len(chunk)
                if (
                    name.startswith("captures/")
                    and path.suffix == ".json"
                    and checksum.hexdigest() != path.stem
                ):
                    raise Conflict("A market-data capture failed its checksum before backup.")
                manifest["files"][name] = checksum.hexdigest()
            archive.writestr("manifest.json", canonical(manifest))
    validate_bundle(temporary)
    temporary.replace(final)
    return final


def validate_bundle(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise Conflict("Backup contains duplicate files or lacks its manifest.")
        if sum(info.file_size for info in archive.infolist()) > 64 * 1024**3:
            raise Conflict("Backup exceeds the supported restore size.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema") != 1 or manifest.get("environment") != "paper":
            raise Conflict("Backup format or environment is unsupported.")
        if set(names) != set(manifest["files"]) | {"manifest.json"}:
            raise Conflict("Backup file inventory differs from its manifest.")
        for name, expected in manifest["files"].items():
            if name != "workspace.sqlite3" and not re.fullmatch(
                r"captures/(?:[a-f0-9]{64}\.json|trades-\d{4}-\d{2}-\d{2}\.jsonl)", name
            ):
                raise Conflict("Backup contains an unexpected path.")
            with archive.open(name) as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            if checksum != expected:
                raise Conflict("Backup checksum failed.")
            if (
                name.startswith("captures/")
                and name.endswith(".json")
                and Path(name).stem != expected
            ):
                raise Conflict("Backup capture identity differs from its checksum.")
    return manifest


def restore_bundle(source: Path, destination: Path):
    manifest = validate_bundle(source)
    if destination.exists():
        raise Conflict(
            "Restore into a new recovery directory; existing state is never overwritten."
        )
    destination.mkdir(parents=True)
    with zipfile.ZipFile(source) as archive:
        for name in manifest["files"]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream, archive.open(name) as archived:
                shutil.copyfileobj(archived, stream, length=512 * 1024)
    with sqlite3.connect(destination / "workspace.sqlite3", factory=Connection) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise Conflict("Restored database failed integrity verification. Do not start it.")
    restored = Store(destination)
    restored.verify()
    with restored.connect() as db:
        manifests = [row[0] for row in db.execute("SELECT id FROM captures")]
    for identity in manifests:
        restored.load_capture(identity)
    restored.set_emergency(True)
    with source.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    restored.event(
        "backup.restored",
        {
            "source_checksum": checksum,
            "reconciliation_required": True,
            "entries_disarmed": True,
        },
    )
    return restored.verify()


def main():
    parser = argparse.ArgumentParser(
        description="Validate and restore paper evidence into a new recovery directory."
    )
    parser.add_argument("backup", type=Path)
    parser.add_argument("recovery_directory", type=Path)
    args = parser.parse_args()
    result = restore_bundle(args.backup.resolve(), args.recovery_directory.resolve())
    print(json.dumps({**result, "emergency_stop": True, "reconciliation_required": True}))


if __name__ == "__main__":
    main()
