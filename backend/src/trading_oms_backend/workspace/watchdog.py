from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from .monitoring import Monitoring
from .store import Store, now


class Watchdog:
    """No broker interface. Persist an emergency and delivery intent before alerting."""

    def __init__(self, directory, pid, *, clock=time.time, monitoring=Monitoring):
        self.directory, self.pid = directory, pid
        self.clock, self.monitoring = clock, monitoring
        self.started, self.alerted = clock(), False

    def tick(self):
        stamp = self.clock()
        try:
            heartbeat = json.loads(
                (self.directory / "engine-health.json").read_text(encoding="utf-8")
            )
            fresh = 0 <= stamp - heartbeat["timestamp"] < 20
            if fresh and heartbeat.get("pid") != self.pid:
                return False  # The new launcher owns monitoring after a restart.
            valid = fresh and heartbeat.get("pid") == self.pid
        except (OSError, ValueError, KeyError, TypeError):
            valid = False
        if valid:
            self.alerted = False
            (self.directory / "watchdog-health.json").write_text(
                json.dumps({"timestamp": stamp, "engine_pid": self.pid}), encoding="utf-8"
            )
        elif not self.alerted and stamp - self.started > 30:
            store = Store(self.directory)
            store.set_emergency(True)
            detail = (
                "The paper engine watchdog detected a missing heartbeat. "
                "New entries are stopped; inspect Gateway and owned-position protection."
            )
            store.put(
                "incident",
                "watchdog",
                {
                    "id": "watchdog",
                    "severity": "critical",
                    "detail": detail,
                    "timestamp": now(),
                    "resolved": False,
                },
            )
            store.event("watchdog.emergency", {"reason": "engine_heartbeat_expired"})
            identity = uuid.uuid4().hex
            item = {
                "id": identity,
                "text": detail,
                "state": "queued",
                "attempts": 0,
                "next_attempt": 0,
                "timestamp": now(),
            }
            store.put("notification", identity, item)
            try:
                passed = self.monitoring(store, lambda: False).deliver("telegram", detail)
            except Exception:
                passed = False
            item.update(
                state="delivered" if passed else "queued", attempts=1, next_attempt=stamp + 4
            )
            store.put("notification", identity, item)
            store.event("watchdog.notification", {"passed": passed})
            self.alerted = True
        return True


def main():
    parser = argparse.ArgumentParser(description="Independent local paper-engine watchdog.")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args()
    monitor = Watchdog(args.state, args.pid)
    while monitor.tick():
        time.sleep(3)


if __name__ == "__main__":
    main()
