import queue
import threading
from types import SimpleNamespace

import pytest

from trading_oms_backend.workspace.broker import GatewayData
from trading_oms_backend.workspace.migration import prepare_workspace
from trading_oms_backend.workspace.migration_snapshot import collect_snapshot
from trading_oms_backend.workspace.store import Store

ENDS = ("positions_end", "orders_end", "completed_orders_end", "executions_end", "account_end")


class SnapshotBroker:
    def __init__(self, events, observations=(), ends=ENDS, paper=True):
        self.events, self.observations, self.ends = events, observations, ends
        self.paper_context = paper
        self.epoch = 1
        self.overflow = threading.Event()
        self.client = SimpleNamespace(isConnected=lambda: not self.closed)
        self.closed = False
        self.requested = False
        self.can_resume_attestation = True

    def emit(self, kind, **payload):
        self.events.put({"type": kind, "epoch": self.epoch, **payload})

    def connect(self):
        self.emit("handshake")
        self.emit("account_context", paper=self.paper_context, count=1)

    def reconcile(self):
        self.requested = True
        for event in self.observations:
            self.emit(**event)
        for kind in self.ends:
            self.emit(kind)

    def attest(self):
        assert self.paper_context

    def disconnect(self):
        self.closed = True


def position(sec_type="CASH", own_account=True):
    return dict(
        kind="position", conid=123, quantity="100", sec_type=sec_type, own_account=own_account
    )


def legacy_store(tmp_path):
    store = Store(tmp_path / "paper")
    store.event(
        "reconciliation.finished",
        {
            "ready": False,
            "positions": [{"conid": 123, "quantity": "100", "own_account": True}],
            "issues": ["Local and broker positions disagree, or external positions are present."],
        },
    )
    return store


def test_stale_untyped_snapshot_is_refreshed_without_rewriting_history(tmp_path):
    store = legacy_store(tmp_path)
    original = store.events()
    brokers = []

    def factory(events):
        broker = SnapshotBroker(events, [position()])
        brokers.append(broker)
        return broker

    prepare_workspace(store.directory, broker_factory=factory)
    assert store.get("migration", "unified_workspace")
    assert store.events()[: len(original)] == original
    assert brokers[0].closed and brokers[0].requested
    assert len(list((store.directory / "backups" / "before-unification").glob("*.zip"))) == 1
    assert any(e["type"] == "migration.snapshot.observed" for e in store.events())
    assert not store.orders() and not store.list("qualification")
    prepare_workspace(store.directory, broker_factory=lambda _: pytest.fail("already migrated"))


@pytest.mark.parametrize(
    "observations",
    [
        [position("STK")],
        [position("")],
        [position("CASH", False)],
        [dict(kind="open_order", broker_id=9, status="Submitted", own_account=True)],
        [dict(kind="open_order", broker_id=9, status="Inactive", own_account=True)],
    ],
)
def test_refresh_cannot_bypass_nonflat_or_unknown_broker_state(tmp_path, observations):
    store = legacy_store(tmp_path)
    with pytest.raises(ValueError):
        prepare_workspace(store.directory, broker_factory=lambda q: SnapshotBroker(q, observations))
    assert not store.get("migration", "unified_workspace")
    assert any(e["type"] == "migration.snapshot.failed" for e in store.events())


def test_local_unknown_order_never_triggers_snapshot_override(tmp_path):
    store = legacy_store(tmp_path)
    store.reserve_order("pending", {"purpose": "exit", "quantity": 1}, "run", 10)
    with pytest.raises(ValueError, match="orders"):
        prepare_workspace(store.directory, broker_factory=lambda _: pytest.fail("unsafe refresh"))
    assert store.orders()[0]["state"] == "reserved"


@pytest.mark.parametrize(
    "observations,ends,paper",
    [
        ([], ENDS[:-1], True),
        ([], ENDS, False),
        ([dict(kind="disconnected")], ENDS, True),
        ([dict(kind="broker_error", code=1100, context="broker")], ENDS, True),
        ([dict(kind="account_context", paper=False, count=1)], ENDS, True),
        ([dict(kind="broker_error", code=1100, context="pnl")], ENDS, True),
    ],
)
def test_incomplete_or_interrupted_snapshot_is_not_migration_evidence(observations, ends, paper):
    broker = None

    def factory(events):
        nonlocal broker
        broker = SnapshotBroker(events, observations, ends, paper)
        return broker

    with pytest.raises(ValueError):
        collect_snapshot(broker_factory=factory, timeout=0.05)
    assert broker.closed


def test_optional_pnl_and_informational_farm_messages_do_not_block_snapshot():
    result = collect_snapshot(
        broker_factory=lambda q: SnapshotBroker(
            q,
            [
                dict(kind="broker_error", code=2119, context="broker"),
                dict(kind="broker_error", code=321, context="pnl"),
                dict(kind="account_context", paper=True, count=1),
            ],
        )
    )
    assert result["paper"] and result["positions"] == []


def test_snapshot_transport_has_no_execution_methods():
    broker = GatewayData(queue.Queue())
    assert broker.execution_enabled is False
    assert not any(
        hasattr(broker, name)
        for name in (
            "submit_crypto",
            "submit_bracket",
            "submit_exit",
            "submit_protection",
            "cancel",
        )
    )


def test_disconnect_during_callback_thread_start_does_not_mask_connection_failure():
    broker = GatewayData(queue.Queue())
    calls = []
    broker.client = SimpleNamespace(disconnect=lambda: calls.append("disconnected"))
    broker.thread = threading.Thread(target=lambda: None)
    broker.disconnect()
    assert calls == ["disconnected"]


def test_callback_overflow_cannot_complete_snapshot():
    def factory(events):
        broker = SnapshotBroker(events)
        broker.overflow.set()
        return broker

    with pytest.raises(ValueError, match="overflow"):
        collect_snapshot(broker_factory=factory)


def test_switch_to_another_paper_account_invalidates_snapshot():
    def factory(events):
        broker = SnapshotBroker(events)
        original = broker.reconcile

        def changed_context():
            original()
            broker.can_resume_attestation = False
            broker.emit("account_context", paper=True, count=1)

        broker.reconcile = changed_context
        return broker

    with pytest.raises(ValueError, match="context"):
        collect_snapshot(broker_factory=factory)


def test_failed_connect_does_not_expose_sdk_exception_text():
    def factory(events):
        broker = SnapshotBroker(events)

        def fail():
            raise RuntimeError("private diagnostic that must not be forwarded")

        broker.connect = fail
        return broker

    with pytest.raises(ValueError, match="127.0.0.1:4002") as error:
        collect_snapshot(broker_factory=factory)
    assert "private diagnostic" not in str(error.value)


def test_launcher_opens_offline_and_defers_snapshot_to_the_application(
    tmp_path, monkeypatch, capsys
):
    from trading_oms_backend.workspace import serve

    calls = []

    def create(directory, token, **kwargs):
        assert directory == tmp_path / "paper"
        assert kwargs["defer_migration"] is True
        calls.append("app")
        return object()

    monkeypatch.setattr(
        "sys.argv",
        [
            "serve",
            "--state",
            str(tmp_path / "paper"),
            "--development",
            "--no-watchdog",
        ],
    )
    monkeypatch.setattr(serve, "create_app", create)
    monkeypatch.setattr(serve.Vault, "write", lambda *a: None)
    monkeypatch.setattr(serve.uvicorn, "run", lambda *a, **k: calls.append("http"))
    serve.main()
    assert calls == ["app", "http"]
    assert "Gateway login can wait" in capsys.readouterr().out
