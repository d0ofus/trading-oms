"""Offline, flat-account migration. Call only while holding both engine locks."""

import json
import uuid
from datetime import UTC, datetime

from .graph import number
from .migration_snapshot import SNAPSHOT_ENDS, collect_snapshot
from .oms import OrderLedger
from .recovery import backup_bundle
from .store import Conflict, Store, now


class MigrationSnapshotRequired(Conflict):
    """The local ledger is flat, but fresh broker observations are required."""


def _validate_fresh_snapshot(snapshot):
    age = (datetime.now(UTC) - datetime.fromisoformat(snapshot["observed_at"])).total_seconds()
    if (
        snapshot.get("source") != "read_only_gateway"
        or snapshot.get("paper") is not True
        or set(snapshot.get("complete", [])) != SNAPSHOT_ENDS
        or not 0 <= age < 30
    ):
        raise Conflict("A complete fresh paper snapshot is required for migration.")
    if any(p.get("own_account") is not True for p in snapshot["positions"]):
        raise Conflict("Migration found an unexpected account position; inspect paper Gateway.")
    if any(number(p["quantity"]) and p.get("sec_type") != "CASH" for p in snapshot["positions"]):
        raise Conflict(
            "Migration found a nonzero security position or unknown instrument type. "
            "Review the positions in paper TWS/Gateway, resolve them manually, and retry. "
            "This check cannot close positions."
        )
    if any(
        o.get("own_account") is not True
        or o.get("status") not in {"Filled", "Cancelled", "ApiCancelled", "Rejected"}
        for o in snapshot["broker_orders"]
    ):
        raise Conflict(
            "Migration found working or unresolved broker orders. Review them in paper "
            "TWS/Gateway and retry after they are terminal. This check cannot cancel orders."
        )
    if any(e.get("own_account") is not True for e in snapshot["executions"]):
        raise Conflict("Migration found an execution from an unexpected account.")


def prepare_workspace(directory, simulator_directory=None, *, broker_factory=None):
    """Call while holding both engine locks; never starts the execution engine."""
    try:
        return migrate_workspace(directory, simulator_directory)
    except MigrationSnapshotRequired:
        store = Store(directory)
        backup = backup_bundle(store, directory / "backups" / "before-unification")
        store.event(
            "migration.snapshot.started", {"source": "read_only_gateway", "backup": backup.name}
        )
        try:
            snapshot = collect_snapshot(broker_factory=broker_factory)
            store.event("migration.snapshot.observed", snapshot)
            migrate_workspace(directory, simulator_directory, snapshot=snapshot, backup=backup)
        except ValueError as exc:
            store.event("migration.snapshot.failed", {"reason": str(exc)})
            raise


def migrate_workspace(directory, simulator_directory=None, *, snapshot=None, backup=None):
    store = Store(directory)
    if store.get("migration", "unified_workspace"):
        return
    if (store.get("workspace", "environment") or {}).get("name", "paper") != "paper":
        raise Conflict("A local simulation directory cannot become a paper broker ledger.")
    ledger = OrderLedger()
    ledger.store = store
    if any(p["quantity"] for p in ledger.owned().values()) or any(
        o["state"] not in {"filled", "cancelled", "rejected"} for o in store.orders()
    ):
        raise Conflict(
            "Migration requires the old paper workspace to be flat with all orders "
            "resolved. Reconcile using the previous version first."
        )
    if any(
        o.get("status") not in {"Filled", "Cancelled", "ApiCancelled", "Rejected"}
        for o in store.list("broker_order")
    ):
        raise Conflict(
            "Migration found unresolved broker orders. Reconcile the old paper workspace first."
        )
    if snapshot is not None:
        _validate_fresh_snapshot(snapshot)
    else:
        with store.connect() as db:
            row = db.execute(
                "SELECT payload FROM events WHERE type='reconciliation.finished' "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        if row:
            observed = json.loads(row[0])
            if not observed.get("ready") or any(
                number(p.get("quantity", 0)) and p.get("sec_type") != "CASH"
                for p in observed.get("positions", [])
            ):
                raise MigrationSnapshotRequired(
                    "The last paper snapshot was not flat and reconciled. "
                    "Open Settings and connect the paper Gateway for a fresh read-only snapshot."
                )
    backup = backup or backup_bundle(store, directory / "backups" / "before-unification")
    archive = None
    if simulator_directory and (simulator_directory / "workspace.sqlite3").exists():
        # Retain the original directory intact, including recorded open positions.
        archive = directory.parent / "archives" / ("local-simulation-" + uuid.uuid4().hex)
        archive.mkdir(parents=True)
        simulator = Store(simulator_directory)
        simulation_backup = backup_bundle(simulator, archive, environment="live_crypto_simulation")
        simulation_backup.rename(archive / "local-simulation.zip")
        (archive / "provenance.json").write_text(
            json.dumps(
                {
                    "environment": "live_crypto_simulation",
                    "execution_provider": "local_simulator",
                    "broker_qualification": False,
                    "archived_at": now(),
                    "original_preserved": True,
                }
            ),
            encoding="utf-8",
        )
    with store.transaction() as db:
        record = {
            "version": 1,
            "timestamp": now(),
            "backup": backup.name,
            "simulation_archive": archive.name if archive else None,
            "historical_records_modified": False,
            "fresh_paper_snapshot": snapshot is not None,
        }
        store.write(db, "migration", "unified_workspace", record)
        store.append(db, "workspace.unified", record)
