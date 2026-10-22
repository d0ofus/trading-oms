import pytest
from test_workspace_engine import BrokerDouble

from trading_oms_backend.workspace.engine import Engine
from trading_oms_backend.workspace.store import Store


def fixture(tmp_path):
    e = Engine(Store(tmp_path), BrokerDouble)
    requests = []
    e.broker.resolve = lambda symbol="", **filters: (
        requests.append((symbol, filters)) or len(requests)
    )
    e.connected = True
    return e, requests


def observation(search, kind="contract", **extra):
    return {
        "type": kind,
        "request": search["request"],
        "epoch": 1,
        "conid": 323608988,
        "symbol": "1810",
        "sec_type": "STK",
        "currency": "HKD",
        "exchange": "SEHK",
        "resolved": True,
        **extra,
    }


def test_search_keeps_route_reports_failure_and_does_not_create_feed_incident(tmp_path):
    e, requests = fixture(tmp_path)
    p = e.resolve("1810", exchange="SMART", conid=323608988)
    e.observe(observation(p, "broker_error", code=200, context="search"))
    status = e.search_status(p["search_id"])
    assert status["state"] == "failed" and status["code"] == 200
    assert not e.incidents.open()
    q = e.resolve("1810", exchange="SEHK", sec_type="STK", currency="HKD", conid=323608988)
    e.observe(observation(q))
    e.observe(observation(q, "contracts_end"))
    status = e.search_status(q["search_id"])
    assert status["state"] == "results" and status["results"][0]["conid"] == 323608988
    assert requests[-1][1]["exchange"] == "SEHK"


def test_search_rejects_mismatched_identity_and_ignores_old_callbacks(tmp_path):
    e, _ = fixture(tmp_path)
    a = e.resolve("1810", conid=323608988, currency="HKD")
    b = e.resolve("1810", conid=323608988, currency="HKD")
    e.observe(observation(a, currency="USD"))
    assert 323608988 not in e.contracts
    e.observe(observation(b))
    e.observe(observation(b, "contracts_end"))
    e.observe(observation(a, currency="USD"))
    assert e.contracts[323608988]["currency"] == "HKD"
    assert e.search_status(a["search_id"])["state"] == "failed"
    e.broker.epoch += 1
    e.observe(observation(b, currency="USD"))
    assert e.contracts[323608988]["currency"] == "HKD"


def test_search_timeout_interruption_and_bounds(tmp_path, monkeypatch):
    import time

    e, _ = fixture(tmp_path)
    clock = [100]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    a = e.resolve("TEST")
    clock[0] += 31
    assert e.search_status(a["search_id"])["state"] == "timed_out"
    e.observe(observation(a))
    assert not e.contracts
    b = e.resolve("TEST")
    e.connected = False
    assert e.search_status(b["search_id"])["state"] == "interrupted"
    e.connected = True
    for _ in range(25):
        c = e.resolve("TEST")
    assert len(e._searches) == 20
    with pytest.raises(ValueError):
        e.search_status(a["search_id"])
    for i in range(250):
        e.observe(observation(c, conid=i + 1))
    status = e.search_status(c["search_id"])
    assert len(status["results"]) == 200 and status["truncated"]


def test_connectivity_errors_cannot_be_hidden_by_search_correlation(tmp_path):
    e, _ = fixture(tmp_path)
    p = e.resolve("1810")
    e.observe(observation(p, "broker_error", code=502, context="search"))
    assert not e.connected
    assert e.search_status(p["search_id"])["state"] == "interrupted"
    assert e.incidents.open()


def test_informational_farm_status_is_not_a_search_failure(tmp_path):
    e, _ = fixture(tmp_path)
    p = e.resolve("1810")
    e.observe(observation(p, "broker_error", code=2104, context="search"))
    assert e.search_status(p["search_id"])["state"] == "searching"
    assert not e.incidents.open()


def test_broker_failures_with_overlapping_numeric_id_are_not_search_results(tmp_path):
    e, _ = fixture(tmp_path)
    p = e.resolve("1810")
    e.observe(observation(p, "broker_error", code=201, context="broker"))
    assert e.incidents.open()[0]["code"] == "broker_201"
    assert e.search_status(p["search_id"])["state"] == "searching"


def test_candidates_stay_in_search_cache_and_eviction_retains_used_contracts(tmp_path):
    e, _ = fixture(tmp_path)
    p = e.resolve("1810")
    e.observe(observation(p, "contract_candidate", resolved=False))
    assert not e.contracts
    assert len(e.search_status(p["search_id"])["results"]) == 1
    resolved = e.resolve("1810")
    e.observe(observation(resolved))
    e.data[323608988] = {"conid": 323608988}
    unused = e.resolve("OTHER")
    e.observe(observation(unused, conid=99, symbol="OTHER"))
    for _ in range(20):
        e.resolve("NEXT")
    assert 323608988 in e.contracts
    assert 99 not in e.contracts


def test_adapter_route_generation_and_safe_service_identity(monkeypatch):
    import queue
    import threading

    from ibapi.client import EClient
    from ibapi.contract import Contract, ContractDetails

    from trading_oms_backend.workspace.broker import PaperGateway

    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    gateway = PaperGateway(queue.Queue())
    gateway.connect()
    gateway._next_id = 100
    requests = []
    monkeypatch.setattr(
        gateway.client, "reqContractDetails", lambda req, c: requests.append((req, c))
    )
    monkeypatch.setattr(gateway.client, "reqMarketRule", lambda *args: None)
    old = gateway.resolve("1810", sec_type="STK", conid=323608988, currency="HKD", exchange="SEHK")
    current = gateway.resolve(
        "1810", sec_type="STK", conid=323608988, currency="HKD", exchange="SEHK"
    )
    assert requests[-1][1].exchange == "SEHK"
    gateway.client.error(current, 0, 201, "Order rejected")
    assert gateway.observations.get_nowait()["context"] == "broker"
    c = Contract()
    c.conId, c.symbol, c.secType, c.currency, c.exchange = 323608988, "1810", "STK", "HKD", "SEHK"
    details = ContractDetails()
    details.contract, details.validExchanges = c, "SEHK"
    gateway.client.contractDetails(current, details)
    gateway.client.contractDetailsEnd(current)
    c_old = Contract()
    c_old.conId, c_old.symbol, c_old.secType, c_old.currency, c_old.exchange = (
        323608988,
        "1810",
        "STK",
        "USD",
        "SMART",
    )
    details.contract = c_old
    gateway.client.contractDetails(old, details)
    assert gateway._contracts[323608988].currency == "HKD"
    gateway.retire_search(old, [])
    gateway.client.error(old, 0, 200, "private diagnostic")
    events = []
    while not gateway.observations.empty():
        events.append(gateway.observations.get_nowait())
    assert events[-1]["context"] == "retired_search"
    assert "private diagnostic" not in str(events)
    gateway.client.error(-1, 0, 2106, "HMDS data farm connection is OK:ushmds")
    assert gateway.observations.get_nowait()["service"]["farm"] == "ushmds"
