import json

from trading_oms_backend.workspace.store import Store
from trading_oms_backend.workspace.watchdog import Watchdog


def test_watchdog_persists_emergency_and_failed_delivery_without_spamming(tmp_path):
    clock = [100.0]

    class FailedDelivery:
        def __init__(self, *_):
            pass

        def deliver(self, *_):
            return False

    monitor = Watchdog(tmp_path, 123, clock=lambda: clock[0], monitoring=FailedDelivery)
    monitor.tick()
    clock[0] = 131
    assert monitor.tick()
    store = Store(tmp_path)
    assert store.emergency()
    assert store.list("notification")[0]["state"] == "queued"
    monitor.tick()
    assert len(store.list("notification")) == 1
    (tmp_path / "engine-health.json").write_text(json.dumps({"pid": 124, "timestamp": 131}))
    assert not monitor.tick()  # An old watchdog cannot stop the restarted engine.


def test_watchdog_refreshes_only_for_its_current_healthy_engine(tmp_path):
    monitor = Watchdog(tmp_path, 123, clock=lambda: 100)
    (tmp_path / "engine-health.json").write_text(json.dumps({"pid": 123, "timestamp": 99}))
    assert monitor.tick()
    assert (tmp_path / "watchdog-health.json").exists()
    assert not Store(tmp_path).emergency()
