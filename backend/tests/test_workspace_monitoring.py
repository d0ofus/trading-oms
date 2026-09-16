import httpx
import pytest

from trading_oms_backend.workspace.monitoring import Monitoring, validate_configuration
from trading_oms_backend.workspace.store import Store


class MemoryVault:
    def __init__(self):
        self.values = {}

    def read(self, key):
        return self.values.get(key)

    def write(self, key, value):
        self.values[key] = value


def test_notification_credentials_stay_outside_journal_and_tests_expire_on_edit(tmp_path):
    vault = MemoryVault()
    monitor = Monitoring(
        Store(tmp_path),
        lambda: True,
        vault=vault,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
    )
    # Construct deliberately synthetic, nonfunctional secrets; no external transport.
    token = "000000:" + "synthetic" * 4
    monitor.configure(token, "000000", "https://hc-ping.com/00000000-0000-0000-0000-000000000000")
    assert monitor.test("telegram")["passed"]
    assert monitor.test("healthchecks")["passed"]
    assert token not in str(monitor.store.events())
    monitor.configure(token, "000000", "https://hc-ping.com/00000000-0000-0000-0000-000000000000")
    assert not monitor.status()["telegram"]["tested"]


def test_notification_errors_do_not_leak_urls_and_redirects_are_not_followed(tmp_path):
    monitor = Monitoring(
        Store(tmp_path),
        lambda: True,
        vault=MemoryVault(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "https://example.invalid"})
        ),
    )
    monitor.configure(
        "000000:" + "fixture" * 5,
        "000000",
        "https://hc-ping.com/00000000-0000-0000-0000-000000000000",
    )
    assert not monitor.test("healthchecks")["passed"]
    with pytest.raises(ValueError):
        validate_configuration(
            "000000:" + "fixture" * 5,
            "000000",
            "https://localhost/00000000-0000-0000-0000-000000000000",
        )


def test_durable_alert_retry_and_heartbeat_stop_when_engine_is_unhealthy(tmp_path):
    from datetime import UTC, datetime

    deliveries = []
    healthy = [False]
    store = Store(tmp_path)
    monitor = Monitoring(store, lambda: healthy[0], vault=MemoryVault())
    monitor.status = lambda: {"configured": True}
    monitor.last_backup_day = datetime.now(UTC).date().isoformat()
    monitor.deliver = lambda channel, *args: deliveries.append(channel) or len(deliveries) > 1
    store.put(
        "notification",
        "test",
        {"id": "test", "state": "queued", "attempts": 0, "text": "Synthetic alert"},
    )
    monitor.tick(100)
    assert store.get("notification", "test")["state"] == "queued"
    monitor.tick(101)
    assert deliveries == ["telegram"]
    monitor.tick(103)
    assert store.get("notification", "test")["state"] == "delivered"
    assert store.get("monitoring", "last_heartbeat") is None
    healthy[0] = True
    monitor.tick(104)
    assert deliveries == ["telegram", "telegram", "healthchecks"]
    healthy[0] = False
    monitor.tick(200)
    assert len(deliveries) == 3
