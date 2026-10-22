from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path

from .health import atomic_health, fresh_health, read_health
from .incidents import IncidentBook
from .monitoring import Monitoring
from .store import Store, now


class Watchdog:
    """No broker interface. Persist an emergency and delivery intent before alerting."""

    def __init__(
        self,
        directory,
        pid,
        *,
        instance,
        clock=time.monotonic,
        wall_clock=time.time,
        monitoring=Monitoring,
    ):
        self.directory, self.pid, self.instance = directory, pid, instance
        self.clock, self.wall_clock, self.monitoring = clock, wall_clock, monitoring
        self.started, self.last_good, self.alerted = clock(), None, False
        self.store = Store(directory)
        self.incidents = IncidentBook(self.store)

    def owns(self, owner):
        return bool(
            owner
            and owner.get("instance") == self.instance
            and owner.get("pid") == self.pid
            and owner.get("state") != "stopped"
        )

    def tick(self):
        import os

        stamp, wall = self.clock(), self.wall_clock()
        owner = self.store.get("workspace", "engine_owner") or {}
        if not self.owns(owner):
            return False
        heartbeat = read_health(self.directory / "engine-health.json")
        valid = (
            heartbeat.get("instance") == self.instance
            and heartbeat.get("pid") == self.pid
            and type(heartbeat.get("sequence")) is int
            and heartbeat["sequence"] > 0
            and fresh_health(heartbeat, 20, wall, stamp)
        )
        if valid:
            self.last_good, self.alerted = heartbeat["monotonic"], False
            with self.store.transaction() as db:
                if not self.owns(self.store.read(db, "workspace", "engine_owner")):
                    return False
                atomic_health(
                    self.directory / "watchdog-health.json",
                    {
                        "version": 1,
                        "timestamp": wall,
                        "monotonic": stamp,
                        "instance": self.instance,
                        "engine_pid": self.pid,
                        "pid": os.getpid(),
                        "state": "monitoring",
                        "engine_sequence": heartbeat["sequence"],
                        "acknowledged": {
                            "timestamp": heartbeat["timestamp"],
                            "monotonic": heartbeat["monotonic"],
                        },
                    },
                )
        elif not self.alerted and (
            stamp - self.started >= 30 if self.last_good is None else stamp - self.last_good >= 20
        ):
            detail = (
                "The paper engine watchdog detected a missing heartbeat. "
                "New entries are stopped; inspect Gateway and owned-position protection."
            )
            identity = uuid.uuid4().hex
            item = {
                "id": identity,
                "text": detail,
                "state": "queued",
                "attempts": 0,
                "next_attempt": 0,
                "timestamp": now(),
            }
            with self.store.transaction() as db:
                current = self.store.read(db, "workspace", "engine_owner") or {}
                if not self.owns(current):
                    return False
                self.store.write(db, "safety", "emergency", {"active": True})
                episode = self.incidents.raise_in(
                    db, "watchdog", detail, self.instance, notify=False
                )
                item["incident_id"] = episode["id"]
                self.store.append(
                    db,
                    "watchdog.emergency",
                    {
                        "reason": "engine_heartbeat_expired",
                        "instance": self.instance,
                    },
                )
                self.store.write(db, "notification", identity, item)
            try:
                passed = self.monitoring(self.store, lambda: False).deliver("telegram", detail)
            except Exception:
                passed = False
            item.update(
                state="delivered" if passed else "queued", attempts=1, next_attempt=wall + 4
            )
            self.store.put("notification", identity, item)
            self.store.event("watchdog.notification", {"passed": passed})
            self.alerted = True
        return True


def main():
    parser = argparse.ArgumentParser(description="Independent local paper-engine watchdog.")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--instance", required=True)
    args = parser.parse_args()
    monitor = Watchdog(args.state, args.pid, instance=args.instance)
    while monitor.tick():
        time.sleep(3)


if __name__ == "__main__":
    main()
