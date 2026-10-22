"""Isolated browser-test service. Its broker cannot open a socket or send orders."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

import uvicorn  # noqa: E402 - resolve the checked-out backend above, not another installed copy.
from trading_oms_backend.workspace.api import create_app  # noqa: E402
from trading_oms_backend.workspace.broker import PaperGateway, PaxosDataGateway  # noqa: E402


class OfflineBroker(PaperGateway):
    def __init__(self, observations):
        super().__init__(observations)
        self.submissions = []

    def resolve(self, symbol="", **filters):
        self._request_id += 1
        request = self._request_id
        if symbol == "BTC" or filters.get("conid") == 456:
            self.emit("contract", request=request, **unified_crypto_contract)
        elif symbol == "1810" or filters.get("conid") == 323608988:
            if filters.get("exchange") == "SEHK":
                self.emit("contract", request=request, **engine.contracts[323608988])
            else:
                self.emit("broker_error", request=request, context="search", code=200)
        self.emit("contracts_end", request=request)
        return request

    def submit_crypto(self, intent):
        self.submissions.append(intent)  # Test-only transport capture; no SDK call.

    def connect(self):
        raise ValueError("Broker networking is disabled in browser verification.")

    def subscribe(self, conid):
        pass

    def submit_bracket(self, intent):
        raise AssertionError("Browser verification must never submit broker orders.")

    def submit_exit(self, intent):
        raise AssertionError("Browser verification must never submit broker orders.")

    def cancel(self, broker_id):
        raise AssertionError("Browser verification must never mutate a broker order.")

    submit_pair = submit_bracket
    submit_fx = submit_bracket
    preview_short = submit_bracket


class OfflineCryptoData(PaxosDataGateway):
    def connect(self):
        raise AssertionError("Crypto browser verification must never open a broker socket.")

    def subscribe(self, conid):
        return True

    def _require_paper(self):
        if not self._attested:
            raise ValueError("The synthetic fixture has not been prepared.")


def serialize_offline_engine(target):
    # start_engine=False omits the production command loop. HTTP reads and fixture
    # callbacks must still share one owner, especially around owned-position caches.
    lock = threading.RLock()
    original = target.call
    from trading_oms_backend.workspace.watchdog import Watchdog
    monitor = Watchdog(target.store.directory, os.getpid(), instance=target.process_identity)

    def call(method, **kwargs):
        with lock:
            target.write_health()
            monitor.tick()
            result = original(method, **kwargs)
            while not target.observations.empty():
                target.observe(target.observations.get_nowait())
            return result

    target.call = call


with tempfile.TemporaryDirectory(
    prefix="oms-browser-", ignore_cleanup_errors=True
) as temporary:
    executable = Path(
        subprocess.check_output(
            [
                "node",
                "-e",
                "process.stdout.write(require('playwright').chromium.executablePath())",
            ],
            cwd=ROOT / "frontend",
            text=True,
        )
    )
    # Use Playwright's matching headless shell, which has no desktop startup
    # services or browser UI. Keep its revision tied to the installed package.
    browser_manifest = json.loads(
        (ROOT / "frontend/node_modules/playwright-core/browsers.json").read_text()
    )
    shell_revision = next(
        item["revision"]
        for item in browser_manifest["browsers"]
        if item["name"] == "chromium-headless-shell"
    )
    shell_root = executable.parents[2] / f"chromium_headless_shell-{shell_revision}"
    shell_name = (
        "chrome-headless-shell.exe" if os.name == "nt" else "chrome-headless-shell"
    )
    executable = next(
        (path for path in shell_root.rglob(shell_name) if path.is_file()),
        shell_root / shell_name,
    )
    if not executable.exists():
        raise RuntimeError(
            "Install the verification browser: cd frontend; npx playwright install chromium"
        )
    browser = subprocess.Popen(
        [
            str(executable),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-proxy-server",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-component-update",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--enable-automation",
            "--no-default-browser-check",
            "--no-first-run",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={Path(temporary) / 'browser'}",
            "about:blank",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    app = create_app(
        Path(temporary),
        "synthetic-browser-pairing-for-tests-only",
        start_engine=False,
        frontend=ROOT / "frontend" / "dist",
        launcher_key="synthetic-browser-pairing-for-tests-only",
        port=8013,
    )
    engine = app.state.engine
    serialize_offline_engine(engine)
    engine.code_verified = False  # Stable fixture; never claim a real release gate.
    engine.broker = OfflineBroker(engine.observations)
    engine.contracts[100] = {
        "conid": 100,
        "symbol": "AAPL",
        "name": "Synthetic contract fixture for browser verification",
        "exchange": "SMART",
        "routing_exchange": "SMART",
        "primary_exchange": "NASDAQ",
        "sec_type": "STK",
        "currency": "USD",
        "resolved": True,
        "min_tick": "0.01",
    }
    unified_crypto_contract = {"conid": 456, "symbol": "BTC", "sec_type": "CRYPTO", "currency": "USD", "exchange": "PAXOS", "routing_exchange": "PAXOS", "market_rule": 1, "min_size": "0.0001", "size_increment": "0.0001", "name": "Synthetic BTC paper test contract", "min_tick": "0.01", "resolved": True}

    def unified_fixture(step: str):
        from trading_oms_backend.workspace.market import Candle
        from trading_oms_backend.workspace.store import now
        if step == "ready":
            engine.broker._accounts = ("DU000000",)
            engine.broker._attested = True
            engine.broker._next_id = 100
            engine.server_version = 220
            engine.code_verified = True
            engine.next_id = 100
            engine.store.set_emergency(False)
            engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
        engine.connected = engine.attested = engine.clock_ok = True
        engine.reconciled = engine.position_agreement = True
        engine.reconciled_at = time.monotonic()
        engine.facts = {"NetLiquidation": "10000", "AvailableFunds": "10000", "GrossPositionValue": "0"}
        engine.data.setdefault(456, {"conid": 456, "symbol": "BTC"}).update(live=True, warm=True, price="100", received_at=now(), source_at=now(), history_loaded=True, data_type="live", candle_source="AGGTRADES")
        engine.quotes[456] = {side: {"price": price, "received_at": now()} for side, price in (("bid", "99.99"), ("ask", "100.01"))}
        runs = [r for r in engine.store.list("run") if r.get("execution") == "crypto_breakout"]
        if step == "warm":
            for run in runs:
                engine._runtime(run)["market"].closed.append(Candle(datetime.now(UTC) - timedelta(minutes=1), Decimal(100), Decimal(101), Decimal(99), Decimal(100), Decimal(10)))
        if step == "entry":
            run = next(r for r in runs if r.get("armed"))
            engine._crypto_enter(run, {"candle": now(), "capture": "synthetic-browser-data"})
        if step in {"entry", "exit"}:
            purpose = "entry" if step == "entry" else "exit"
            order = next(o for o in engine.store.orders() if o["payload"].get("execution") == "crypto_breakout" and o["payload"]["purpose"] == purpose)
            payload = order["payload"]
            engine.observe({"type": "open_order", "broker_id": order["broker_id"], "client_id": engine.broker.client_id, "conid": 456, "symbol": "BTC", "own_account": True, "reference": "oms-" + order["id"], "action": "BUY" if purpose == "entry" else "SELL", "order_type": "MKT", "tif": "IOC", "parent_id": 0, "quantity": payload["quantity"], "cash_quantity": payload.get("cash_quantity"), "filled": "0.25", "status": "Filled"})
            engine.observe({"type": "execution", "broker_id": order["broker_id"], "client_id": engine.broker.client_id, "execution_id": "fixture-" + order["id"], "own_account": True, "conid": 456, "symbol": "BTC", "side": "BOT" if purpose == "entry" else "SLD", "quantity": "0.25", "price": "100"})
            engine.positions = {456: {"conid": 456, "symbol": "BTC", "sec_type": "CRYPTO", "currency": "USD", "exchange": "PAXOS", "own_account": True, "quantity": str(engine.owned()[runs[-1]["id"]]["quantity"])}}
            engine._finish_reconcile()
        if step == "outage":
            engine.requested_connection = True
            engine._connection_lost("Synthetic outage")
            engine._outage_tick()
        if step == "recovery":
            engine._finish_reconcile()
            engine._outage_tick()
        return {"step": step, "submissions": len(engine.broker.submissions)}

    engine.unified_fixture = unified_fixture

    def stock_fixture(valued=False):
        # Synthetic contract evidence only. This service cannot submit stock orders.
        from trading_oms_backend.workspace.store import now
        rules = {"revision": 1, "source": "operator_verified", "reference": "TWS contract details", "calendar": "XHKG", "currency": "HKD", "quantity_increment": "200", "minimum_quantity": "200", "exit_increment": "1", "price_scale": "1", "fee_reserve": "25", "same_day_resale": True, "broker_protection": True, "native_oca": True, "local_protection": True, "fractional_protection": False}
        stock = {"conid": 323608988, "symbol": "1810", "sec_type": "STK", "currency": "HKD", "exchange": "SEHK", "routing_exchange": "SEHK", "primary_exchange": "SEHK", "market_rule": 1, "order_types": ["MKT", "LMT", "STP"], "name": "Synthetic stock fixture", "min_tick": "0.01", "resolved": True, "stock_rules": rules}
        from trading_oms_backend.workspace.stock_references import reference_day
        stock.update(min_size="200", size_increment="200", price_magnifier=1)
        engine.store.put("stock_reference", "HKEX", {"business_date": reference_day(), "retrieved_at": now(), "source": "Synthetic HKEX fixture", "revision": "fixture", "rows": {"1810": {"symbol": "1810", "board_lot": "200", "currency": "HKD"}}})
        engine.contracts[stock["conid"]] = stock
        engine.contracts[456] = unified_crypto_contract
        engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
        engine.data[stock["conid"]] = {"conid": stock["conid"], "symbol": "1810", "live": True, "warm": True, "price": "30", "received_at": now(), "source_at": now(), "history_loaded": True}
        engine.quotes[stock["conid"]] = {side: {"price": "30", "received_at": now()} for side in ("bid", "ask")}
        engine.fx_quotes.pop(("USD", "HKD"), None)
        if valued:
            engine.fx_quotes[("USD", "HKD")] = {"base": "USD", "quote": "HKD", "bid": "7.8", "ask": "7.82", "live": True, "received_at": now()}
        return {"synthetic": True}

    engine.stock_fixture = stock_fixture

    def preparation_fixture():
        from trading_oms_backend.workspace.store import now

        day = datetime.now(UTC).strftime("%Y%m%d")
        stock = {
            "conid": 107113386, "symbol": "META", "sec_type": "STK", "currency": "USD",
            "exchange": "NASDAQ", "routing_exchange": "NASDAQ", "primary_exchange": "NASDAQ",
            "market_rule": 1, "order_types": ["LMT", "MKT", "STP", "GTD"], "resolved": True,
            "min_size": "0.0001", "size_increment": "0.0001", "price_magnifier": 1,
            "time_zone": "US/Eastern", "trading_hours": f"{day}:0400-{day}:2000",
            "liquid_hours": f"{day}:0930-{day}:1600", "name": "Synthetic META fixture",
        }
        engine.contracts[stock["conid"]] = stock
        engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
        engine.data[stock["conid"]] = {"conid": stock["conid"], "symbol": "META", "live": True,
            "warm": False, "price": "600", "received_at": now(), "source_at": now()}
        engine.quotes[stock["conid"]] = {side: {"price": "600", "received_at": now()} for side in ("bid", "ask")}
        return {"synthetic": True}

    engine.preparation_fixture = preparation_fixture

    def fx_fixture():
        from trading_oms_backend.workspace.store import now

        day = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y%m%d")
        following = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y%m%d")
        conid = 14433401
        contract = {
            "conid": conid, "symbol": "AUD", "currency": "USD", "sec_type": "CASH",
            "exchange": "IDEALPRO", "routing_exchange": "IDEALPRO", "resolved": True,
            "min_size": "1", "size_increment": "1", "min_tick": "0.00005", "market_rule": 991,
            "order_types": ["MKT", "LMT", "STP"], "time_zone": "US/Eastern",
            "trading_hours": f"{day}:0000-{following}:1700", "name": "Synthetic AUD.USD fixture",
            "metadata_instance": engine.process_identity, "metadata_epoch": engine.broker.epoch,
        }
        engine.contracts[conid] = contract
        engine.market_rules[991] = [{"low": "0", "increment": "0.00005"}]
        engine._stock_market_rule_context = {991: (engine.process_identity, engine.broker.epoch)}
        engine.data[conid] = {"conid": conid, "symbol": "AUD", "live": True, "warm": False,
                              "history_loaded": True, "subscription_status": "subscribed"}
        cache = engine._fx_cache(conid)
        cache.update(selected_source="MIDPOINT", fx_midpoint={"price": "0.65005", "valid": True,
                    "source_at": now(), "received_at": now()}, fx_bidask={"bid": "0.65",
                    "ask": "0.6501", "valid": True, "source_at": now(), "received_at": now()})
        for source in ("MIDPOINT", "BID", "ASK"):
            engine._fx_source(conid, source).update(status="completed", epoch=engine.broker.epoch)
        cache["feeds"] = {kind: {"status": "healthy", "attempts": 0, "epoch": engine.broker.epoch}
                          for kind in ("fx_bidask", "fx_midpoint")}
        # Only preparation/presentation is exercised. Keep the fixture offline.
        engine.connected = engine.attested = False
        engine.operator_disconnected = True
        return {"synthetic": True, "submissions": len(engine.broker.submissions)}

    engine.fx_fixture = fx_fixture

    @app.post("/fixture/fx")
    def apply_fx_fixture():
        return engine.call("fx_fixture")

    def fx_policy_fixture():
        from trading_oms_backend.workspace.fx_strategies import fx_copy
        from trading_oms_backend.workspace.stock_strategies import stock_templates

        fx_fixture()
        engine.contracts[14433401].update(min_size="0.01", size_increment="0.01")
        draft = engine.store.save_draft(None, "Legacy FX policy fixture",
            fx_copy(stock_templates(8)[-1]["document"]), 0)
        engine.store.publish(draft["id"], draft["revision"])
        compatible = engine.fx_compatibility(draft["id"], 1, 14433401, "broker_held")
        run = engine.create_run(draft["id"], 1, 14433401, {"quantity": "0.01"},
            "broker_held", compatible["plan"]["hash"], "fx")
        return {"run": run, "submissions": len(engine.broker.submissions)}

    engine.fx_policy_fixture = fx_policy_fixture

    @app.post("/fixture/fx-policy")
    def apply_fx_policy_fixture():
        return engine.call("fx_policy_fixture")

    @app.post("/fixture/fx-scheduling/{stage}")
    def fx_scheduling_fixture(stage: str):
        from trading_oms_backend.workspace.engine import Engine
        from trading_oms_backend.workspace.store import Store, now

        class SchedulingBroker(OfflineBroker):
            def data_contract_ready(self, conid):
                return conid == 14433401

            def start_feed(self, conid, kind):
                assert conid == 14433401
                self._request_id += 1
                self.register_feed(self._request_id, conid, kind)
                return self._request_id

            def history(self, conid, **kwargs):
                assert conid == 14433401, "Inactive stock history must not be requested"
                return self.start_feed(conid, "history")

        with tempfile.TemporaryDirectory(prefix="oms-fx-browser-data-") as folder:
            target = Engine(Store(Path(folder)), SchedulingBroker)
            stamp = datetime.now(UTC)
            day = (stamp - timedelta(days=1)).strftime("%Y%m%d")
            following = (stamp + timedelta(days=2)).strftime("%Y%m%d")
            conid = 14433401
            target.contracts[conid] = {
                "conid": conid, "symbol": "AUD", "currency": "USD", "sec_type": "CASH",
                "exchange": "IDEALPRO", "routing_exchange": "IDEALPRO", "resolved": True,
                "time_zone": "US/Eastern", "trading_hours": f"{day}:0000-{following}:1700",
            }
            target.subscribe(conid)
            target.data[conid].update(live=True, data_type="live")
            target.quotes[conid] = {side: {"price": price, "received_at": now()}
                                    for side, price in (("bid", "0.65"), ("ask", "0.6501"))}
            for stock in (641568851, 107113386):
                target.store.put("run", str(stock), {
                    "id": str(stock), "conid": stock, "execution": "stock_breakout",
                    "armed": False, "position": "0", "state": "paused",
                    "binding": {"execution_plan": {"session_mode": "premarket_regular"}},
                })
                target.store.put("subscription", str(stock), {"conid": stock, "active": False})
            target.connected = target.attested = True
            target._next_health_write = target.next_reconcile = target.next_heartbeat = float("inf")
            cache = target._fx_cache(conid)
            if stage != "queued":
                target.maintain()
                cache["next_tick"] = 0  # Advance only the isolated pacing fixture.
                target._fx_data_maintain()
                for kind in ("fx_bidask", "fx_midpoint"):
                    target.observe({"type": kind, "conid": conid, "epoch": target.broker.epoch,
                        "request": cache["feeds"][kind]["request"], "timestamp": stamp.timestamp(),
                        "bid": "0.65", "ask": "0.6501", "price": "0.65005", "received_at": now()})
                h = cache["sources"]["MIDPOINT"]
                base = {"conid": conid, "request": h["request"], "epoch": target.broker.epoch,
                        "signal_source": "MIDPOINT"}
                target.observe({**base, "type": "historical_bar", "timestamp": str(int(stamp.timestamp()) // 60 * 60 - 60),
                                "open": "0.65", "high": "0.6501", "low": "0.65", "close": "0.65005"})
                target.observe({**base, "type": "history_end"})
            return {"data": target.data_snapshot()[0], "candles": target.candles(conid),
                    "incidents": target.incidents.open(), "orders": target.store.orders()}

    @app.post("/fixture/preparation")
    def apply_preparation_fixture():
        return engine.call("preparation_fixture")

    @app.post("/fixture/stocks")
    def apply_stock_fixture():
        return engine.call("stock_fixture")

    @app.post("/fixture/stocks-valued")
    def apply_valued_stock_fixture():
        return engine.call("stock_fixture", valued=True)

    @app.post("/fixture/unified/{step}")
    def apply_unified_fixture(step: str):
        return engine.call("unified_fixture", step=step)

    crypto_app = create_app(
        Path(temporary) / "crypto",
        "synthetic-crypto-browser-pairing-only",
        start_engine=False,
        frontend=ROOT / "frontend" / "dist",
        environment="live_crypto_simulation",
        port=8014,
    )
    crypto_engine = crypto_app.state.engine
    serialize_offline_engine(crypto_engine)
    crypto_engine.broker.data = OfflineCryptoData(crypto_engine.observations)
    crypto_engine.code_verified = False
    crypto_engine.data[1] = {
        "conid": 1, "symbol": "BTC", "live": True, "warm": False,
        "history_loaded": True, "received_at": None, "price": "60000",
        "history_progress": {"minute_bars": 14400, "fine_bars": 720,
                             "complete_reference_sessions": 10, "required_reference_sessions": 10},
    }
    crypto_engine.quotes[1] = {
        "bid": {"price": "59999.75", "received_at": "2026-09-20T00:00:00+00:00"},
        "ask": {"price": "60000.25", "received_at": "2026-09-20T00:00:00+00:00"},
    }

    def oca_fixture(step: str):
        """Only this isolated test server exposes deterministic local feed controls."""
        from trading_oms_backend.workspace.market import Candle
        from trading_oms_backend.workspace.store import now

        data = crypto_engine.broker.data
        if step == "ready":
            data._accounts = ("DU000000",)  # Synthetic fixture; never a real account.
            data._attested = True
            data._next_id = 100
            crypto_engine.connected = crypto_engine.attested = crypto_engine.clock_ok = True
            crypto_engine.server_version = 220
            crypto_engine.code_verified = True  # Synthetic fixture, never release evidence.
            crypto_engine.next_id = 100
            contract = {"conid": 1, "symbol": "BTC", "sec_type": "CRYPTO", "currency": "USD",
                        "exchange": "PAXOS", "market_rule": 1, "min_size": "0.0001", "size_increment": "0.0001",
                        "name": "Synthetic BTC for local execution tests", "min_tick": "0.01"}
            crypto_engine.contracts[1] = contract
            crypto_engine.broker.set_contract(contract)
            crypto_engine.market_rules[1] = [{"low": "0", "increment": "0.01"}]
        stamp = now()
        crypto_engine.data[1].update(warm=True, live=True, received_at=stamp, source_at=stamp, price="100")
        for side, price in (("bid", "99.99"), ("ask", "100.01")):
            crypto_engine.quotes[1][side] = {"price": price, "received_at": stamp}
        crypto_engine.broker.on_market({"type": "data_type", "conid": 1, "live": True})

        def feed(kind, **payload):
            data.sequence += 1
            crypto_engine.broker.on_market({"type": kind, "conid": 1, "sequence": data.sequence,
                                            "timestamp": datetime.now(UTC).timestamp(), **payload})
            while not crypto_engine.observations.empty():
                crypto_engine.observe(crypto_engine.observations.get_nowait())

        if step == "warm":
            for run in crypto_engine.store.list("run"):
                state = crypto_engine._runtime(run)
                state["market"].closed.append(Candle(datetime.now(UTC) - timedelta(minutes=1),
                                                     Decimal(100), Decimal(101), Decimal(99), Decimal(100), Decimal(10)))
        if step == "minute":
            run = next(r for r in crypto_engine.store.list("run") if r.get("armed"))
            crypto_engine._oca_submit(run, {"candle": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "high": "101", "low": "99", "expires_at": (datetime.now(UTC) + timedelta(seconds=45)).isoformat(),
                "capture": "synthetic-browser-candle", "authorization_id": run["authorization_id"]})
        if step in {"long", "short"}:
            feed("quote", side="ask" if step == "short" else "bid", price="100")
            feed("tick", price="99" if step == "short" else "101", size="1")
            feed("quote", side="bid" if step == "short" else "ask", price="99" if step == "short" else "101")
        if step == "exit":
            feed("quote", side="bid", price="100")
            feed("quote", side="ask", price="100")
        crypto_engine.begin_reconcile()
        while not crypto_engine.observations.empty():
            crypto_engine.observe(crypto_engine.observations.get_nowait())
        crypto_engine._oca_maintain()
        return {"state": step}

    crypto_engine.oca_fixture = oca_fixture

    @crypto_app.post("/fixture/oca/{step}")
    def apply_oca_fixture(step: str):
        return crypto_engine.call("oca_fixture", step=step)

    crypto_app.router.routes.insert(0, crypto_app.router.routes.pop())
    crypto_server = uvicorn.Server(uvicorn.Config(crypto_app, host="127.0.0.1", port=8014,
                                                access_log=False, log_level="warning"))
    crypto_thread = threading.Thread(target=crypto_server.run, daemon=True)
    crypto_thread.start()

    # Separate legacy ledger verifies HTTP startup with no Gateway. Only the
    # migration collector runs; its injected transport cannot open a socket.
    from trading_oms_backend.workspace.store import Conflict, Store

    offline_store = Store(Path(temporary) / "offline-paper")
    offline_store.event("reconciliation.finished", {"ready": False, "positions": []})
    offline_app = create_app(
        offline_store.directory, "synthetic-offline-browser-pairing-only",
        start_engine=False, frontend=ROOT / "frontend" / "dist",
        development=True, port=8015, defer_migration=True,
    )

    def unavailable_gateway(_):
        raise Conflict("Read-only migration check received Gateway code 502. Open paper Gateway on 127.0.0.1:4002, then retry.")

    offline_app.state.engine.migration.broker_factory = unavailable_gateway
    offline_app.state.engine.start()
    offline_server = uvicorn.Server(uvicorn.Config(
        offline_app, host="127.0.0.1", port=8015, access_log=False, log_level="warning",
    ))
    offline_thread = threading.Thread(target=offline_server.run, daemon=True)
    offline_thread.start()
    try:
        # The HTTP fixture must not advertise readiness before the independent
        # browser exposes CDP (cold Windows browser startup can take longer).
        deadline = time.monotonic() + 45
        opener = build_opener(ProxyHandler({}))
        port_file = Path(temporary) / "browser" / "DevToolsActivePort"
        while True:
            if browser.poll() is not None:
                raise RuntimeError(
                    "The isolated verification browser exited during startup."
                )
            try:
                debug_port = int(port_file.read_text(encoding="utf-8").splitlines()[0])
                with opener.open(
                    f"http://127.0.0.1:{debug_port}/json/version", timeout=1
                ) as response:
                    if response.status == 200:
                        endpoint = json.load(response)["webSocketDebuggerUrl"]
                        break
            except (URLError, TimeoutError, OSError, ValueError, IndexError):
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "The isolated verification browser did not become ready."
                )
            time.sleep(0.2)

        @app.get("/browser-endpoint")
        def browser_endpoint():
            return {"endpoint": endpoint}

        # Place the fixture route ahead of the production SPA catch-all.
        app.router.routes.insert(0, app.router.routes.pop())

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8013,
            access_log=False,
            log_level="warning",
            timeout_graceful_shutdown=3,
        )
    finally:
        offline_server.should_exit = True
        offline_thread.join(timeout=8)
        crypto_server.should_exit = True
        crypto_thread.join(timeout=5)
        if os.name == "nt" and browser.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(browser.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif browser.poll() is None:
            browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()
