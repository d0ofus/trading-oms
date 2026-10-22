"""Offline UI startup with execution disabled until legacy migration completes."""

import threading
from concurrent.futures import Future

from .migration import MigrationSnapshotRequired, migrate_workspace
from .migration_snapshot import collect_snapshot
from .recovery import backup_bundle
from .store import Conflict, Store


class DeferredMigration:
    """Both directory locks must remain held by the launcher for this lifetime."""

    def __init__(self, directory, simulator_directory=None, *, broker_factory=None):
        self.directory, self.simulator_directory = directory, simulator_directory
        self.broker_factory = broker_factory
        self.pending, self.status, self.detail = False, "complete", "Workspace migration complete."
        self.worker = self.result = None
        self.cancelled = threading.Event()
        self.next_health = 0.0
        store = Store(directory)
        store.verify()
        if (store.get("workspace", "environment") or {}).get("name", "paper") != "paper":
            raise Conflict("A local simulation directory cannot become a paper broker ledger.")
        try:
            migrate_workspace(directory, simulator_directory)
        except Conflict as exc:
            self.pending, self.status, self.detail = True, "pending", str(exc)
            self.refresh_allowed = isinstance(exc, MigrationSnapshotRequired)
            # Preserve the legacy state before the UI can edit drafts/settings.
            self.backup = backup_bundle(store, directory / "backups" / "before-unification")
            store.event("migration.deferred", {"reason": self.detail, "backup": self.backup.name})

    def snapshot(self):
        return {"pending": self.pending, "status": self.status, "detail": self.detail}

    def dispatch(self, engine, method, kwargs):
        if method in {
            "snapshot",
            "overview",
            "candles",
            "order_detail",
            "incident_detail",
            "incident_current",
        }:
            return getattr(engine, method)(**kwargs)
        if method == "connect":
            if self.status == "checking":
                return {"state": "checking_migration", "detail": self.detail}
            if not self.refresh_allowed:
                self.status = "blocked"
                return {"state": "migration_blocked", "detail": self.detail}
            self.cancelled.clear()
            self.result = Future()
            self.status = "checking"
            self.detail = (
                "Reading paper Gateway for migration (up to 30 seconds). "
                "No orders can be sent or cancelled."
            )
            engine.store.event("migration.snapshot.started", {"source": "read_only_gateway"})
            self.worker = threading.Thread(
                target=self._collect, name="migration-check", daemon=True
            )
            self.worker.start()
            return {"state": "checking_migration", "detail": self.detail}
        if method in {"disconnect", "shutdown"}:
            if self.status == "checking" and not self.cancelled.is_set():
                engine.store.event("migration.snapshot.cancel_requested", {"reason": method})
            self.cancelled.set()
            return {"state": "disconnected"}
        if method == "emergency" and kwargs.get("active") is True:
            engine.store.set_emergency(True)
            return {"active": True}
        raise Conflict(
            "Workspace migration is pending. Open Settings and connect the paper Gateway "
            "to complete the read-only check before execution actions. " + self.detail
        )

    def _collect(self):
        try:
            self.result.set_result(
                collect_snapshot(
                    broker_factory=self.broker_factory,
                    cancelled=self.cancelled,
                )
            )
        except Exception as exc:
            self.result.set_exception(
                exc
                if isinstance(exc, Conflict)
                else Conflict(
                    "The migration check failed. Review the paper Gateway connection and retry."
                )
            )

    def maintain(self, engine):
        if self.result is None or not self.result.done():
            return
        result, self.result = self.result, None
        try:
            if self.cancelled.is_set():
                raise Conflict("Migration check cancelled. Connect paper Gateway when ready.")
            snapshot = result.result()
            engine.store.event("migration.snapshot.observed", snapshot)
            migrate_workspace(
                self.directory,
                self.simulator_directory,
                snapshot=snapshot,
                backup=self.backup,
            )
        except Exception as exc:
            self.status, self.detail = (
                "blocked",
                (
                    str(exc)
                    if isinstance(exc, Conflict)
                    else (
                        "Could not finish workspace migration. Check local storage and retry; "
                        "execution remains disabled."
                    )
                ),
            )
            engine.store.event("migration.snapshot.failed", {"reason": self.detail})
            return
        # Only the execution owner activates the paper engine, after the read-only
        # adapter has disconnected and all original migration guards have passed.
        self.pending, self.status, self.detail = False, "complete", "Workspace migration complete."
        engine.activate_after_migration()

    def close(self):
        self.cancelled.set()
        if self.worker:
            self.worker.join(timeout=5)
