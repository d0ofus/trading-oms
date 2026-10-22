import queue
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
from test_workspace_fx_policy import fx_contract

from trading_oms_backend.workspace.api import create_app
from trading_oms_backend.workspace.broker import PaperGateway
from trading_oms_backend.workspace.stock_strategies import stock_templates


def test_authenticated_fx_copy_and_binding_preserve_original(tmp_path, monkeypatch):
    app = create_app(tmp_path, "synthetic-fx-api-pairing", start_engine=False)
    engine = app.state.engine
    monkeypatch.setattr(engine.broker, "subscribe", lambda conid: None)
    engine.contracts[14433401] = fx_contract()
    engine.market_rules[1] = [{"low": "0", "increment": "0.00005"}]
    original = engine.store.save_draft(
        None, "Original stock", stock_templates(8)[-1]["document"], 0
    )
    published = engine.store.publish(original["id"], original["revision"])
    origin = "http://127.0.0.1:8000"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        body = {"name": original["name"], "document": original["document"]}
        assert client.post("/api/strategies/convert-fx", json=body).status_code == 401
        assert client.post("/api/auth/pair", json={"token": "synthetic-fx-api-pairing"}).is_success
        copied = client.post("/api/strategies/convert-fx", json=body).json()
        assert copied["id"] != original["id"]
        assert copied["document"]["schema_version"] == 9
        assert client.post(
            f"/api/strategies/{copied['id']}/publish", json={"revision": copied["revision"]}
        ).is_success
        request = {
            "strategy_id": copied["id"],
            "version": 1,
            "conid": 14433401,
            "session_mode": "fx",
            "protection_type": "locally_monitored",
            "sizing": {"quantity": "25000"},
        }
        compatible = client.post("/api/runs/compatibility", json=request).json()
        assert compatible["plan"]["signal_source"] == "MIDPOINT"
        assert client.post("/api/runs", json=request).status_code == 409
        request["execution_plan_revision"] = compatible["plan"]["hash"]
        result = client.post("/api/runs", json=request)
        assert result.is_success, result.text
        assert result.json()["binding"]["sizing"]["quantity"] == "25000"
        assert result.json()["binding"]["sizing"]["notional"] is None
    assert engine.store.version(original["id"], 1)["hash"] == published["hash"]
    assert list((tmp_path / "backups").glob("*.sqlite3"))
    assert not engine.store.orders()


def test_sdk_fx_callbacks_are_timestamped_and_history_uses_requested_series(monkeypatch):
    from ibapi.client import EClient

    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    gateway = PaperGateway(queue.Queue())
    gateway.connect()
    client = gateway.client
    gateway._contracts[14433401] = SimpleNamespace(secType="CASH", exchange="IDEALPRO")
    requests = []
    monkeypatch.setattr(client, "reqTickByTickData", lambda *a: requests.append(a))
    midpoint = gateway.start_feed(14433401, "fx_midpoint")
    bidask = gateway.start_feed(14433401, "fx_bidask")
    assert [r[2] for r in requests] == ["MidPoint", "BidAsk"]
    client.tickByTickMidPoint(midpoint, 1800000000, 0.65005)
    client.tickByTickBidAsk(
        bidask, 1800000000, 0.65, 0.6501, 1, 1, SimpleNamespace(bidPastLow=False, askPastHigh=False)
    )
    events = [gateway.observations.get_nowait() for _ in range(2)]
    assert [e["type"] for e in events] == ["fx_midpoint", "fx_bidask"]
    assert all(e["received_at"] and e["generation"] == e["request"] for e in events)
    monkeypatch.setattr(client, "cancelTickByTickData", lambda *a: None)
    gateway.cancel_feed(midpoint)
    client.tickByTickMidPoint(midpoint, 1800000001, 9)
    assert gateway.observations.empty()
    historical = []
    monkeypatch.setattr(client, "reqHistoricalData", lambda *a: historical.append(a))
    for source in ("MIDPOINT", "BID", "ASK"):
        gateway.history(14433401, use_rth=False, signal_source=source)
    assert [r[5:7] for r in historical] == [("MIDPOINT", 0), ("BID", 0), ("ASK", 0)]
    gateway.connect()
    client.tickByTickBidAsk(
        bidask, 1800000002, 9, 10, 1, 1, SimpleNamespace(bidPastLow=False, askPastHigh=False)
    )
    assert gateway.observations.empty()
