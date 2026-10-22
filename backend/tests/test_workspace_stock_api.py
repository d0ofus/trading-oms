"""Authenticated stock policy bindings and native-funding adapter observations."""

import queue
import threading

from fastapi.testclient import TestClient
from test_workspace_automatic_rules import cache_reference
from test_workspace_stock_policy import contract

from trading_oms_backend.workspace.api import create_app
from trading_oms_backend.workspace.broker import PaperGateway
from trading_oms_backend.workspace.stock_strategies import stock_templates


def test_stock_endpoints_require_authentication_and_preserve_revision_evidence(
    tmp_path, monkeypatch
):
    app = create_app(tmp_path, "synthetic-stock-api-pairing", start_engine=False)
    engine = app.state.engine
    cache_reference(engine)
    monkeypatch.setattr(engine.broker, "subscribe", lambda conid: None)
    c = contract()
    c.update(
        min_size="200",
        size_increment="200",
        price_magnifier=1,
        reference_data={"status": "ready", "symbol": "1810", "currency": "HKD", "board_lot": "200"},
    )
    rules = c.pop("stock_rules")
    engine.contracts[c["conid"]] = c
    draft = engine.store.save_draft(None, "Stock API fixture", stock_templates()[-1]["document"], 0)
    published = engine.store.publish(draft["id"], draft["revision"])
    origin = "http://127.0.0.1:8000"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        path = f"/api/contracts/{c['conid']}/stock-rules"
        assert client.post(path, json={"rules": rules}).status_code == 401
        assert client.post(
            "/api/auth/pair", json={"token": "synthetic-stock-api-pairing"}
        ).is_success
        assert client.post(path, json={"rules": rules}).is_success
        assert client.post(path, json={"rules": rules}).status_code == 409
        body = {"strategy_id": draft["id"], "version": 1, "conid": c["conid"]}
        result = client.post("/api/runs/compatibility", json=body).json()
        assert result["status"] == "needs_qualification"
        assert client.post("/api/runs", json=body).status_code == 409
        body["execution_plan_revision"] = result["plan"]["hash"]
        run = client.post("/api/runs", json=body)
        assert run.is_success, run.text
        assert run.json()["binding"]["strategy_hash"] == published["hash"]
        assert run.json()["binding"]["sizing"]["notional"] == "25"
        assert list((tmp_path / "backups").iterdir())


def test_native_ledger_is_account_specific_and_accepts_prefixed_cash(monkeypatch):
    from ibapi.client import EClient

    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    gateway = PaperGateway(queue.Queue())
    gateway.connect()  # Both network and worker startup are replaced above.
    gateway._accounts = ("DU000000",)  # Synthetic fixture, not a configured account.
    client = gateway.client
    gateway._account_pending = {904}
    gateway._snapshot_requests[904] = "fixture"
    for tag in ("CashBalance", "$LEDGER-SettledCash"):
        client.accountUpdateMulti(904, "DU000000", "", tag, "10000", "HKD")
    for account in ("All", "DU000001", "U000000"):
        client.accountUpdateMulti(904, account, "", "CashBalance", "999999", "HKD")
    observations = [gateway.observations.get_nowait() for _ in range(2)]
    assert gateway.observations.empty()
    assert [e["tag"] for e in observations] == ["CashBalance", "SettledCash"]
    assert all(e["currency"] == "HKD" and e["received_at"] for e in observations)
    assert "DU000000" not in str(observations)
    gateway._account_pending.clear()
    client.accountUpdateMulti(904, "DU000000", "", "CashBalance", "999999", "HKD")
    assert gateway.observations.empty()  # A retired callback cannot refresh new evidence.
    calls = []
    for method in (
        "cancelPositions",
        "reqPositions",
        "reqPositionsMulti",
        "reqAllOpenOrders",
        "reqCompletedOrders",
        "reqExecutions",
        "reqAccountSummary",
        "reqPnL",
        "reqAccountUpdatesMulti",
    ):
        monkeypatch.setattr(
            client, method, lambda *args, method=method: calls.append((method, args))
        )
    gateway.reconcile()
    assert any(
        name == "reqAccountUpdatesMulti" and args[1:] == ("DU000000", "", True)
        for name, args in calls
    )
    assert len([c for c in calls if c[0] == "reqAccountSummary"]) == 1


def test_retired_connection_cannot_refresh_current_price_rules(monkeypatch):
    from types import SimpleNamespace

    from ibapi.client import EClient

    monkeypatch.setattr(EClient, "connect", lambda *args: None)
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    gateway = PaperGateway(queue.Queue())
    gateway.connect()
    old_client = gateway.client
    gateway.connect()
    increment = SimpleNamespace(lowEdge=0, increment=0.01)
    old_client.marketRule(1912, [increment])
    assert gateway.observations.empty()
    gateway.client.marketRule(1912, [increment])
    assert gateway.observations.get_nowait()["type"] == "market_rule"


def test_preparation_allowance_and_library_lifecycle_are_authenticated(tmp_path, monkeypatch):
    from test_workspace_preparation_policy import meta

    app = create_app(tmp_path, "synthetic-preparation-api-pairing", start_engine=False)
    e = app.state.engine
    monkeypatch.setattr(e.broker, "subscribe", lambda conid: None)
    c = meta()
    e.contracts[c["conid"]] = c
    d = e.store.save_draft(None, "API lifecycle", stock_templates()[-1]["document"], 0)
    v = e.store.publish(d["id"], d["revision"])
    origin = "http://127.0.0.1:8000"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        fee_path = f"/api/contracts/{c['conid']}/fee-allowance"
        fee = {"amount": "1", "revision": 0}
        assert client.post(fee_path, json=fee).status_code == 401
        assert (
            client.post("/api/strategies/removal-preview", json={"ids": [d["id"]]}).status_code
            == 401
        )
        client.post("/api/auth/pair", json={"token": "synthetic-preparation-api-pairing"})
        assert client.post(fee_path, json=fee).is_success
        assert client.post(fee_path, json=fee).status_code == 409
        body = {
            "strategy_id": d["id"],
            "version": 1,
            "conid": c["conid"],
            "protection_type": "locally_monitored",
            "session_mode": "premarket_regular",
        }
        result = client.post("/api/runs/compatibility", json=body).json()
        assert result["can_prepare"] and result["arming_requirements"]
        assert result["evidence"]["minimum_quantity"]["source"] == "documented_support"
        body["execution_plan_revision"] = result["plan"]["hash"]
        p = client.post("/api/strategies/removal-preview", json={"ids": [d["id"]]}).json()
        confirm = {"preview_id": p["preview_id"], "mutation_id": "a" * 32}
        response = client.post("/api/strategies/removal-confirm", json=confirm)
        assert response.is_success, response.text
        assert (
            client.post("/api/strategies/removal-confirm", json=confirm).json() == response.json()
        )
        assert client.post("/api/runs", json=body).status_code == 409
        assert e.store.version(d["id"], 1) == v
        assert client.post(f"/api/strategies/{d['id']}/restore").is_success
        assert client.post("/api/runs", json=body).is_success
