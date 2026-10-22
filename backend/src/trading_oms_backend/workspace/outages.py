"""Durable outage notices contain no broker identifiers or credentials."""

import time
import uuid

from .graph import number
from .store import now


class OutageNotifications:
    def _outage_tick(self):
        previous = self.store.get("connection_outage", "current") or {}
        suspended = any(
            number(p.get("quantity", 0)) > 0
            and not self._crypto_valid_protection(
                self.owned().get(
                    p["run_id"], {"run_id": p["run_id"], "conid": 0, "entry_id": "", "quantity": 0}
                )
            )
            for p in self.store.list("crypto_protection")
        )
        suspended = suspended or any(
            position["quantity"] != 0
            and self._stock_run(run := self.store.get("run", position["run_id"]))
            and run.get("protection_type") == "locally_monitored"
            and self._stock_local_suspended(position)
            for position in self.owned().values()
        )
        dependencies = self._data_dependencies()
        failed = suspended or (
            bool(dependencies["runs"] or dependencies["priority"])
            and self.requested_connection
            and not self.connected
        )
        recovered = self.connected and self.attested and self.reconciled and not suspended
        clock = time.time()
        text = None
        if failed and not previous.get("active"):
            previous = {
                "id": uuid.uuid4().hex,
                "active": True,
                "started_at": now(),
                "last_notice": clock,
            }
            text = (
                "IBKR paper connection/data interrupted; affected local protection is "
                "suspended. "
                + (
                    "Connection recovery is enabled. "
                    if self.requested_connection
                    else "Reconnect explicitly to resume recovery. "
                )
                + "Positions are retained; new "
                "entries require fresh arming."
            )
        elif previous.get("active") and recovered:
            previous.update(active=False, recovered_at=now())
            text = (
                "IBKR paper connection recovered and ownership reconciled. Existing local "
                "protection has resumed where needed. Review and manually arm before new "
                "entries."
            )
        elif previous.get("active") and suspended and previous.get("severity") != "critical":
            previous["last_notice"] = clock
            text = (
                "IBKR paper recovery remains unresolved. Inspect the workspace; local "
                "protection may be suspended. No position is closed solely because of this "
                "outage."
            )
        if text:
            previous["severity"] = (
                "critical" if suspended else "warning" if previous.get("active") else "info"
            )
            notification_id = uuid.uuid4().hex
            with self.store.transaction() as db:
                self.store.write(db, "connection_outage", "current", previous)
                self.store.write(
                    db,
                    "notification",
                    notification_id,
                    {
                        "id": notification_id,
                        "text": text,
                        "state": "queued",
                        "created_at": now(),
                        "attempts": 0,
                    },
                )
                self.store.append(
                    db,
                    "connection.outage.notice",
                    {"outage_id": previous["id"], "active": previous["active"], "detail": text},
                )
