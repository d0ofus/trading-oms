import copy
import time
from types import SimpleNamespace

import pytest
from test_workspace_fx_execution import fixture

from trading_oms_backend.workspace.broker import GatewayData


def inactive_stock(engine, fx_run, conid=641568851):
    run = copy.deepcopy(fx_run)
    run.update(
        id=f"inactive-stock-{conid}",
        conid=conid,
        execution="stock_breakout",
        armed=False,
        position="0",
        state="paused",
    )
    run["binding"]["execution_plan"].update(family="stock", session_mode="premarket_regular")
    engine.store.put("run", run["id"], run)
    engine.store.put("subscription", str(conid), {"conid": conid, "active": False})
    return run


def test_paused_unsubscribed_stock_history_cannot_starve_fx(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    inactive_stock(engine, run)
    inactive_stock(engine, run, 107113386)
    engine.next_reconcile = engine.next_heartbeat = float("inf")
    adapter = SimpleNamespace(_contracts={run["conid"]: object()}, client=object())
    requested = []

    def history(conid, *args, **kwargs):
        requested.append(conid)
        if conid != run["conid"]:
            return GatewayData.history(adapter, conid, *args, **kwargs)
        return 600

    monkeypatch.setattr(engine.broker, "history", history)
    cache = engine._fx_cache(run["conid"])
    cache["sources"]["MIDPOINT"]["status"] = "queued"
    for state in cache["feeds"].values():
        state["status"] = "queued"
    engine.maintain()
    engine.maintain()
    assert requested == [run["conid"]]
    assert cache["sources"]["MIDPOINT"]["status"] == "pending"
    assert cache["feeds"]["fx_bidask"]["status"] == "pending"
    assert not engine.incidents.open()
    assert not engine.broker.submitted


def test_initial_fx_queue_is_not_a_retry(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = engine._fx_cache(run["conid"])
    for state in (*cache["feeds"].values(), *cache["sources"].values()):
        state.update(status="queued", attempts=0)
    result = engine._fx_feed_projection(run["conid"])
    assert all(not state["retry_pending"] for state in result.values())
    assert all(state["request_state"] == "queued" for state in result.values())
    assert all(state["retry_in_seconds"] is None for state in result.values())


@pytest.mark.parametrize("source", ["MIDPOINT", "BID", "ASK"])
def test_signal_badge_follows_its_actual_timestamped_feed(tmp_path, monkeypatch, source):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = engine._fx_cache(run["conid"])
    kind = "fx_midpoint" if source == "MIDPOINT" else "fx_bidask"
    state = cache["feeds"][kind]
    state.update(status="queued")
    result = engine._fx_feed_projection(run["conid"], {source})["trade"]
    assert result["signal_source"] == source
    assert result["status"] == "pending"
    assert result["request_state"] == "queued"
    state.update(status="healthy")
    result = engine._fx_feed_projection(run["conid"], {source})["trade"]
    assert result["status"] == "healthy"
    assert result["request_state"] == "receiving"


def test_all_history_families_share_two_pending_requests(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    cache = engine._fx_cache(run["conid"])
    cache["sources"]["MIDPOINT"]["status"] = "queued"
    engine.history_pending[10] = (time.monotonic(), 1)
    engine.premarket_history = {2: {"status": "pending"}}
    calls = []
    monkeypatch.setattr(engine.broker, "history", lambda *a, **kw: calls.append(a) or 600)
    engine._fx_data_maintain()
    assert not calls


@pytest.mark.parametrize(
    "dependency", ["armed", "suspended", "position", "reservation", "exit", "protection"]
)
def test_paused_run_with_current_risk_retains_dependencies(tmp_path, monkeypatch, dependency):
    engine, fx_run = fixture(tmp_path, monkeypatch)
    run = inactive_stock(engine, fx_run)
    if dependency in {"armed", "suspended", "position"}:
        run.update(
            {
                "armed": {"armed": True},
                "suspended": {"authorization_status": "temporarily_suspended"},
                "position": {"position": "1"},
            }[dependency]
        )
        engine.store.put("run", run["id"], run)
    else:
        kind = {
            "reservation": "reservation",
            "exit": "exit_request",
            "protection": "stock_protection",
        }[dependency]
        engine.store.put(
            kind,
            run["id"],
            {
                "run_id": run["id"],
                "conid": run["conid"],
                "active": True,
                "quantity": "1",
                "state": "monitoring",
            },
        )
        if dependency == "exit":
            engine.store.put(
                "exit_request", run["id"], {"requested_at": "2026-09-24T00:00:00+00:00"}
            )
    result = engine._data_dependencies()
    assert run["conid"] in result["contracts"]
    assert run["conid"] in result["premarket"]


def test_required_unresolved_job_waits_while_fx_progresses(tmp_path, monkeypatch):
    engine, fx_run = fixture(tmp_path, monkeypatch)
    run = inactive_stock(engine, fx_run)
    run["position"] = "1"
    engine.store.put("run", run["id"], run)
    calls, resolutions = [], []
    monkeypatch.setattr(
        engine.broker, "data_contract_ready", lambda c: c == fx_run["conid"], raising=False
    )
    monkeypatch.setattr(
        engine.broker, "resolve", lambda **kw: resolutions.append(kw), raising=False
    )
    monkeypatch.setattr(engine.broker, "history", lambda c, **kw: calls.append(c) or 901)
    engine._fx_cache(fx_run["conid"])["sources"]["MIDPOINT"]["status"] = "queued"
    engine._premarket_maintain(time.monotonic())
    engine._premarket_maintain(time.monotonic())
    assert calls == [fx_run["conid"]]
    assert [r["conid"] for r in resolutions] == [run["conid"]]
    assert engine.premarket_history[run["conid"]]["request_state"] == "waiting_contract"
    assert not engine.incidents.open()


def test_history_startup_exception_is_recorded_once_and_other_jobs_continue(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    stock = inactive_stock(engine, run)
    engine.store.put("subscription", str(stock["conid"]), {"conid": stock["conid"], "active": True})
    engine.contracts[stock["conid"]] = {"conid": stock["conid"], "sec_type": "STK"}
    cache = engine._fx_cache(run["conid"])
    cache["sources"]["MIDPOINT"]["status"] = "queued"
    failures, completed = [], []

    def history(c, **kw):
        if c == stock["conid"]:
            failures.append(c)
            raise RuntimeError("synthetic startup fault")
        completed.append(c)
        return 900

    monkeypatch.setattr(engine.broker, "history", history)
    engine._premarket_maintain(time.monotonic())
    engine._premarket_maintain(time.monotonic())
    assert failures == [stock["conid"]]
    assert completed == [run["conid"]]
    assert engine.premarket_history[stock["conid"]]["status"] == "failed"
    incidents = engine.incidents.open()
    assert len(incidents) == 1 and incidents[0]["code"] == "data_request_failure"
    assert incidents[0]["occurrences"] == 1
    assert not engine.broker.submitted


def test_retirement_cancels_requests_and_retains_downloaded_bars(tmp_path, monkeypatch):
    engine, run = fixture(tmp_path, monkeypatch)
    old = inactive_stock(engine, run)
    engine._premarket_queue(old["conid"])
    h = engine.premarket_history[old["conid"]]
    h.update(status="pending", request=905, started=time.monotonic())
    h["bars"][60]["123"] = {"high": "10"}
    cancelled = []
    monkeypatch.setattr(engine.broker, "cancel_feed", lambda r: cancelled.append(r), raising=False)
    engine._retire_data_jobs()
    engine._retire_data_jobs()
    assert h["status"] == "retired" and h["bars"][60]["123"]["high"] == "10"
    assert cancelled == [905]
    assert engine.store.get("run", old["id"])["state"] == "paused"


def test_sdk_resolution_readiness_is_bound_to_connection_epoch(monkeypatch):
    import queue
    import threading

    from ibapi.client import EClient
    from ibapi.contract import Contract, ContractDetails

    monkeypatch.setattr(EClient, "connect", lambda *a: None)
    monkeypatch.setattr(EClient, "isConnected", lambda *a: True)
    monkeypatch.setattr(threading.Thread, "start", lambda *a: None)
    gateway = GatewayData(queue.Queue())
    gateway.connect()
    old_client = gateway.client
    details = ContractDetails()
    details.contract = Contract()
    details.contract.conId = 14433401
    details.contract.symbol, details.contract.currency = "AUD", "USD"
    details.contract.secType, details.contract.exchange = "CASH", "IDEALPRO"
    gateway._search_filters[100] = {"conid": 14433401, "started": time.monotonic()}
    old_client.contractDetails(100, details)
    assert gateway.data_contract_ready(14433401)
    gateway.connect()
    assert not gateway.data_contract_ready(14433401)
    gateway._search_filters[101] = {"conid": 14433401, "started": time.monotonic()}
    old_client.contractDetails(101, details)
    assert not gateway.data_contract_ready(14433401)
    gateway.client.contractDetails(101, details)
    assert gateway.data_contract_ready(14433401)


@pytest.mark.parametrize("server_version", [226, 227])
def test_gateway_226_summary_cancellation_uses_sdk_legacy_format_only(monkeypatch, server_version):
    import queue
    import threading

    from ibapi.client import EClient
    from ibapi.message import OUT

    monkeypatch.setattr(EClient, "connect", lambda *a: None)
    monkeypatch.setattr(threading.Thread, "start", lambda *a: None)
    gateway = GatewayData(queue.Queue())
    gateway.connect()
    client = gateway.client
    monkeypatch.setattr(client, "serverVersion", lambda: server_version)
    monkeypatch.setattr(client, "isConnected", lambda: True)
    legacy, protobuf = [], []
    monkeypatch.setattr(client, "sendMsg", lambda *args: legacy.append(args))
    monkeypatch.setattr(client, "sendMsgProtoBuf", lambda *args: protobuf.append(args))
    client.cancelAccountSummary(902)
    if server_version == 226:
        assert legacy == [(OUT.CANCEL_ACCOUNT_SUMMARY, "1\x00902\x00")]
        assert not protobuf
    else:
        assert protobuf and not legacy
    assert client.useProtoBuf(OUT.PLACE_ORDER) == EClient.useProtoBuf(client, OUT.PLACE_ORDER)
