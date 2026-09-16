"""Deterministic broker double using the production outbox and observation reducer."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from .oms import OrderLedger
from .store import Store


class ReplayOMS(OrderLedger):
    def __init__(self, directory, graph, ticks):
        self.store = Store(directory)
        self.broker = SimpleNamespace(client_id=71)
        self.runtime = {}
        self.run_id = uuid.uuid4().hex
        self.symbol = graph.document["settings"]["symbol"]
        self.capture = self.store.capture({"source": "replay_ticks", "ticks": ticks})
        self.store.put(
            "run",
            self.run_id,
            {
                "id": self.run_id,
                "armed": True,
                "mode": "simulation",
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
        self.store.event(
            "replay.authorized",
            {
                "run_id": self.run_id,
                "strategy_hash": graph.digest,
                "capture": self.capture,
                "broker": "deterministic_fake",
            },
        )

    def incident(self, code, detail):
        raise ValueError(f"Replay observation failed: {code}: {detail}")

    def entry(self, payload):
        identity = uuid.uuid4().hex
        payload = {
            **payload,
            "purpose": "entry",
            "conid": 1,
            "symbol": self.symbol,
            "capture": self.capture,
        }
        quantity, limit, stop = payload["quantity"], payload["limit"], payload["stop"]
        for field in ("limit", "stop", "target"):
            if payload.get(field) is not None:
                payload[field] = str(payload[field])
        order = self.store.reserve_order(
            identity,
            payload,
            self.run_id,
            100,
            {
                "symbol": self.symbol,
                "risk": str(quantity * (limit - stop)),
                "notional": str(quantity * limit),
            },
        )
        self.store.mark_dispatch(identity)
        self._order_observation({"broker_id": order["broker_id"], "status": "Submitted"})
        return order

    def fill(self, order, price, *, exit=False):
        broker_id = order["broker_id"] + (2 if exit else 0)
        self._execution(
            {
                "type": "execution",
                "client_id": 71,
                "broker_id": broker_id,
                "execution_id": f"replay-{broker_id}.01",
                "conid": 1,
                "symbol": self.symbol,
                "side": "SLD" if exit else "BOT",
                "quantity": str(order["quantity"]),
                "price": str(price),
            }
        )
        self._order_observation({"broker_id": broker_id, "status": "Filled"})
        if exit:
            self.release(order)

    def cancel(self, order):
        self._order_observation({"broker_id": order["broker_id"], "status": "Cancelled"})
        self.release(order)

    def release(self, order):
        with self.store.transaction() as db:
            reservation = self.store.read(db, "reservation", order["id"])
            reservation["active"] = False
            self.store.write(db, "reservation", order["id"], reservation)
            self.store.append(db, "risk.released", {"id": order["id"], "simulation": True})
