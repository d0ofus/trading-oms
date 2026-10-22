"""Durable local fills composed with a data-only Paxos connection.

Only the engine thread calls this adapter. A simulator transaction commits before
observations are emitted; reconciliation replays committed executions after crashes.
No method delegates order operations to the SDK transport.
"""

from datetime import UTC, datetime
from decimal import Decimal

from .broker import PaxosDataGateway
from .graph import number
from .oca import is_pair, pair_legs, protection_price
from .store import Conflict, now

TERMINAL = {"Filled", "Cancelled", "Rejected", "ApiCancelled"}


class CryptoSimulator:
    def __init__(self, observations, store, data_factory=PaxosDataGateway):
        self.store = store
        self.data = data_factory(observations)
        self.contracts, self.quotes, self.live = {}, {}, {}
        self.state = store.get("simulator", "ledger") or {
            "cash": "10000",
            "positions": {},
            "orders": {},
            "executions": [],
            "baseline_day": now()[:10],
            "baseline_equity": "10000",
        }
        # A restart never leaves an unfilled entry authorized. Protection and
        # exit orders remain local and resume only with a verified fresh feed.
        for order in self.state["orders"].values():
            if self._is_entry(order) and order["status"] not in TERMINAL:
                self._cancel_group_entry(order)
            elif order["status"] not in TERMINAL:
                order["accepted_sequence"] = 0
                order["trigger_sequence"] = 0
        self._save("simulation.restored", {"entries_disarmed": True})

    @property
    def client_id(self):
        return self.data.client_id

    @staticmethod
    def _is_entry(order):
        return (
            order.get("purpose", "entry" if order["action"] == "BUY" else "protection") == "entry"
        )

    @property
    def epoch(self):
        return self.data.epoch

    @property
    def overflow(self):
        return self.data.overflow

    @property
    def paper_context(self):
        return self.data.paper_context

    @property
    def can_resume_attestation(self):
        return self.data.can_resume_attestation

    def connect(self):
        self.quotes.clear()
        self.live.clear()
        self.data.connect()

    def disconnect(self):
        self.quotes.clear()
        self.live.clear()
        self.data.disconnect()

    def attest(self):
        self.data.attest()

    def heartbeat(self):
        self.data.heartbeat()

    def resolve(self, symbol):
        return self.data.resolve(symbol)

    def subscribe(self, conid):
        return self.data.subscribe(conid)

    def retry_feed(self, conid, component):
        return self.data.retry_feed(conid, component)

    def cancel_feed(self, request):
        return self.data.cancel_feed(request)

    def feed_event_current(self, event):
        return self.data.feed_event_current(event)

    def feed_error_current(self, event):
        return self.data.feed_error_current(event)

    def unsubscribe(self, conid):
        self.data.unsubscribe(conid)
        self.quotes.pop(conid, None)
        self.live.pop(conid, None)

    def reset_subscriptions(self):
        self.quotes.clear()
        self.live.clear()
        self.data.reset_subscriptions()

    def history(self, conid, end="", seconds=60):
        return self.data.history(conid, end, seconds)

    def set_contract(self, contract):
        if (
            contract.get("sec_type") != "CRYPTO"
            or contract.get("exchange") != "PAXOS"
            or contract.get("currency") != "USD"
            or contract.get("symbol") not in {"BTC", "ETH"}
        ):
            raise Conflict("A qualified USD Paxos crypto contract is required.")
        self.contracts[contract["conid"]] = contract

    def _save(self, kind, payload):
        try:
            with self.store.transaction() as db:
                self.store.write(db, "simulator", "ledger", self.state)
                self.store.append(db, kind, {"simulation": True, **payload})
        except Exception:
            # Never let a later reconciliation publish a fill that failed to commit.
            committed = self.store.get("simulator", "ledger")
            if committed is not None:
                self.state = committed
            raise

    def _emit_orders(self):
        for order in self.state["orders"].values():
            self.data.emit("open_order", **self._observation(order))

    @staticmethod
    def _observation(order):
        return {
            k: v
            for k, v in order.items()
            if k not in {"accepted_sequence", "expires_at", "triggered", "trigger_sequence"}
        }

    def _order(
        self,
        intent,
        broker_id,
        action,
        kind,
        *,
        parent=0,
        price=None,
        status="Submitted",
        group=None,
    ):
        entry = intent.get("entry_id", intent["id"])
        return {
            "broker_id": broker_id,
            "client_id": self.client_id,
            "permanent_id": broker_id,
            "own_account": True,
            "reference": "oms-" + intent["id"],
            "conid": intent["conid"],
            "symbol": intent["symbol"],
            "sec_type": "CRYPTO",
            "currency": "USD",
            "exchange": "PAXOS",
            "quantity": str(number(intent["quantity"])),
            "filled": "0",
            "action": action,
            "order_type": kind,
            "parent_id": parent,
            "status": status,
            "limit": str(price) if kind == "LMT" else None,
            "stop": str(price) if kind == "STP" else None,
            "tif": "GTD" if action == "BUY" else "GTC" if parent or kind == "STP" else "DAY",
            "oca_type": 2 if action == "SELL" else 0,
            "oca_group": group or ("oms-" + entry if action == "SELL" else ""),
            "accepted_sequence": self.data.sequence,
            "expires_at": intent.get("expires_at"),
            "simulation": True,
        }

    def _validate_intent(self, intent):
        self.data._require_paper()
        contract = self.contracts.get(intent["conid"])
        if not contract:
            raise Conflict("Resolve the crypto contract before local execution.")
        quantity = number(intent["quantity"])
        increment, minimum = (
            number(contract.get("size_increment", 0)),
            number(contract.get("min_size", 0)),
        )
        if increment <= 0 or minimum <= 0 or quantity < minimum or quantity % increment:
            raise Conflict("The local order quantity does not match qualified increments.")
        durable = next((o for o in self.store.orders() if o["id"] == intent["id"]), None)
        if not durable or durable["state"] != "dispatching":
            raise Conflict("Persist and risk-check the intent before local execution.")
        if intent["broker_id"] != durable["broker_id"] or any(
            intent.get(key) != value for key, value in durable["payload"].items()
        ):
            raise Conflict("The local dispatch differs from its durable intent.")
        return durable

    def submit_bracket(self, intent):
        durable = self._validate_intent(intent)
        if str(intent["broker_id"]) in self.state["orders"]:
            raise Conflict("The local intent was already accepted; reconcile it.")
        run = self.store.get("run", durable["run_id"]) or {}
        quantity, limit, stop = (
            number(intent["quantity"]),
            number(intent["limit"]),
            number(intent["stop"]),
        )
        if self.store.emergency() or not run.get("armed") or run.get("expires_at", "") <= now():
            raise Conflict("Current authorization is required for local entries.")
        if (
            not 0 < stop < limit
            or quantity * limit > 1000
            or quantity * (limit - stop) > 10
            or quantity * limit > number(self.state["cash"])
        ):
            raise Conflict("Local entry exceeds funds, protection or risk limits.")
        if (
            not 0
            < (datetime.fromisoformat(intent["expires_at"]) - datetime.now(UTC)).total_seconds()
            <= 31
        ):
            raise Conflict("The local entry deadline expired.")
        base = intent["broker_id"]
        orders = [self._order(intent, base, "BUY", "LMT", price=limit)]
        if intent.get("target"):
            if number(intent["target"]) <= limit:
                raise Conflict("The local target must exceed the entry limit.")
            orders.append(
                self._order(
                    intent,
                    base + 1,
                    "SELL",
                    "LMT",
                    parent=base,
                    price=intent["target"],
                    status="PreSubmitted",
                )
            )
        orders.append(
            self._order(
                intent, base + 2, "SELL", "STP", parent=base, price=stop, status="PreSubmitted"
            )
        )
        self.state["orders"].update({str(o["broker_id"]): o for o in orders})
        self._save("simulation.bracket.accepted", {"id": intent["id"]})
        self._emit_orders()

    def submit_pair(self, intent):
        durable = self._validate_intent(intent)
        run = self.store.get("run", durable["run_id"]) or {}
        if self.store.emergency() or not run.get("armed") or run.get("expires_at", "") <= now():
            raise Conflict("Current authorization is required for paired entries.")
        if (
            not 0
            < (datetime.fromisoformat(intent["expires_at"]) - datetime.now(UTC)).total_seconds()
            <= 60
        ):
            raise Conflict("The paired entry candle expired.")
        quantity, prices = number(intent["quantity"]), intent["prices"]
        high, low = number(prices["long_entry"]), number(prices["short_entry"])
        risk = quantity * (high - number(prices["long_stop"]) + number(prices["short_stop"]) - low)
        if (
            not 0 < low < high
            or not 0 < risk <= 10
            or quantity * (high + low)
            > min(Decimal(1000), number(self.account_values()[0]["AvailableFunds"]))
        ):
            raise Conflict("Paired entries exceed combined risk or available cash.")
        legs = pair_legs(intent)
        if any(str(leg["broker_id"]) in self.state["orders"] for leg in legs.values()):
            raise Conflict("The local pair already exists; reconcile it.")
        for leg in legs.values():
            order = self._order(
                intent,
                leg["broker_id"],
                leg["action"],
                "STP",
                price=leg["stop"],
                parent=leg["parent_id"],
                status="Submitted" if leg["purpose"] == "entry" else "PreSubmitted",
            )
            order.update(leg, price_rules=intent["price_rules"])
            self.state["orders"][str(leg["broker_id"])] = order
        self._save("simulation.pair.accepted", {"id": intent["id"], "legs": list(legs.values())})
        self._emit_orders()

    def amend_protection(self, intent, amendment):
        self.data._require_paper()
        order = self.state["orders"].get(str(amendment["broker_id"]))
        if (
            not order
            or order.get("group_id") != intent.get("entry_id", intent["id"])
            or order["purpose"] != "protection"
        ):
            raise Conflict("Only a known paired protective stop can be amended.")
        position = self.state["positions"].get(str(intent["conid"]), {})
        held = number(position.get("quantity", 0))
        if (
            not held
            or order["status"] in TERMINAL
            or number(amendment["quantity"]) != abs(held)
            or order["action"] != ("SELL" if held > 0 else "BUY")
        ):
            raise Conflict("Protection must match the signed local holding.")
        order.update(quantity=amendment["quantity"], stop=amendment["stop"], status="Submitted")
        self._save("simulation.protection.amended", amendment)
        self._emit_orders()

    def _submit_sell(self, intent, kind):
        self._validate_intent(intent)
        if str(intent["broker_id"]) in self.state["orders"]:
            raise Conflict("The local sell intent was already accepted.")
        position = self.state["positions"].get(str(intent["conid"]), {})
        held = number(position.get("quantity", 0))
        action = intent.get("action", "SELL")
        if not 0 < number(intent["quantity"]) <= abs(held) or action != (
            "SELL" if held > 0 else "BUY"
        ):
            raise Conflict("Local exits cannot exceed or increase the signed position.")
        price = number(intent["stop" if kind == "STP" else "limit"])
        if price <= 0:
            raise Conflict("A positive local sell price is required.")
        order = self._order(intent, intent["broker_id"], action, kind, price=price)
        order.update(
            purpose=intent.get("purpose", "exit"),
            oca_group="oms-" + intent.get("exit_group", intent["entry_id"]),
            oca_type=2,
            tif="GTC" if kind == "STP" else "DAY",
        )
        if intent.get("pair_recovery"):
            order["group_id"] = intent["entry_id"]
        self.state["orders"][str(order["broker_id"])] = order
        self._save("simulation.sell.accepted", {"id": intent["id"]})
        self._emit_orders()

    def submit_exit(self, intent):
        self._submit_sell(intent, "LMT")

    def submit_protection(self, intent):
        self._submit_sell(intent, "STP")

    def _cancel_group_entry(self, order):
        order["status"] = "Cancelled"
        for child in self.state["orders"].values():
            if child.get("parent_id") == order["broker_id"] and child["status"] not in TERMINAL:
                child["status"] = "Cancelled"

    def cancel(self, broker_id):
        order = self.state["orders"].get(str(broker_id))
        if not order:
            raise Conflict("Unknown local order; reconcile before cancellation.")
        if order["status"] not in TERMINAL:
            if self._is_entry(order):
                self._cancel_group_entry(order)
            else:
                order["status"] = "Cancelled"
            self._save("simulation.order.cancelled", {"broker_id": broker_id})
        self._emit_orders()

    def _reject_entry(self, order, reason):
        group_id = order.get("group_id")
        if not group_id:
            self.cancel(order["broker_id"])
            return
        for member in self.state["orders"].values():
            if member.get("group_id") == group_id and member["status"] not in TERMINAL:
                member["status"] = "Cancelled"
        self._save("simulation.pair.cancelled", {"id": group_id, "reason": reason})
        self._emit_orders()

    def on_market(self, event):
        conid = event.get("conid")
        if event["type"] == "data_type":
            self.live[conid] = event["live"]
            return
        if event["type"] not in {"quote", "tick"}:
            return
        if event["type"] == "quote":
            price = number(event["price"])
            if price <= 0:
                return
            self.quotes.setdefault(conid, {})[event["side"]] = {"price": price, "at": now()}
        if not self.live.get(conid):
            return
        try:
            self.data._require_paper()
        except ValueError:
            return
        for order in list(self.state["orders"].values()):
            if (
                order["conid"] != conid
                or order["status"] != "Submitted"
                or event.get("sequence", 0) <= order["accepted_sequence"]
            ):
                continue
            if self._is_entry(order):
                durable = next(
                    o
                    for o in self.store.orders()
                    if o["id"] == order.get("group_id") or o["broker_id"] == order["broker_id"]
                )
                run = self.store.get("run", durable["run_id"]) or {}
                if (
                    self.store.emergency()
                    or not run.get("armed")
                    or run.get("expires_at", "") <= now()
                    or order["expires_at"] <= now()
                ):
                    self.cancel(order["broker_id"])
                    continue
            if order["order_type"] == "STP" and event["type"] == "tick":
                if (
                    abs(datetime.now(UTC).timestamp() - event["timestamp"]) <= 15
                    and (
                        number(event["price"]) >= number(order["stop"])
                        if order["action"] == "BUY"
                        else number(event["price"]) <= number(order["stop"])
                    )
                    and not order.get("triggered")
                ):
                    order.update(triggered=True, trigger_sequence=event.get("sequence", 0))
                    self._save("simulation.stop.triggered", {"broker_id": order["broker_id"]})
                continue
            side = "ask" if order["action"] == "BUY" else "bid"
            if event["type"] != "quote" or event["side"] != side:
                continue
            price = number(event["price"])
            if order["order_type"] == "STP":
                eligible = order.get("triggered") and event.get("sequence", 0) > order.get(
                    "trigger_sequence", 0
                )
            else:
                eligible = (
                    price <= number(order["limit"])
                    if side == "ask"
                    else price >= number(order["limit"])
                )
            if eligible:
                quotes = self.quotes.get(conid, {})
                if any(
                    side not in quotes
                    or (
                        datetime.now(UTC) - datetime.fromisoformat(quotes[side]["at"])
                    ).total_seconds()
                    > 15
                    for side in ("bid", "ask")
                ):
                    continue
                self._fill(order, price, event.get("sequence", 0), event.get("capture"))

    def _fill(self, order, price, sequence, capture=None):
        quantity = number(order["quantity"])
        stop_after_fill = None
        if self._is_entry(order) and order.get("group_id"):
            try:
                stop_after_fill = protection_price(price, order["direction"], order["price_rules"])
            except ValueError:
                # Local fills are not committed if the new price cannot be protected.
                self._reject_entry(order, "invalid_protection_increment")
                return
        position = self.state["positions"].setdefault(
            str(order["conid"]),
            {
                "conid": order["conid"],
                "symbol": order["symbol"],
                "quantity": "0",
                "average": "0",
                "own_account": True,
                "sec_type": "CRYPTO",
                "currency": "USD",
                "exchange": "PAXOS",
            },
        )
        held = number(position["quantity"])
        entry = self._is_entry(order)
        sign = 1 if order["action"] == "BUY" else -1
        if not entry and (held * sign >= 0 or quantity > abs(held)):
            raise Conflict("Local OCA protection prevents an exit from reversing the position.")
        if entry and (
            held or quantity * price > number(self.account_values()[0]["AvailableFunds"])
        ):
            self._reject_entry(order, "position_or_funds_changed")
            return
        if entry:
            position["average"] = str(price)
        position["quantity"] = str(held + sign * quantity)
        self.state["cash"] = str(number(self.state["cash"]) - sign * quantity * price)
        order.update(status="Filled", filled=str(quantity))
        execution = {
            "execution_id": f"simulation-{order['broker_id']}.01",
            "broker_id": order["broker_id"],
            "client_id": self.client_id,
            "own_account": True,
            "conid": order["conid"],
            "symbol": order["symbol"],
            "side": "BOT" if sign == 1 else "SLD",
            "quantity": str(quantity),
            "price": str(price),
            "simulation": True,
            "quote_capture": capture,
        }
        self.state["executions"].append(execution)
        for other in self.state["orders"].values():
            if (
                entry
                and other["parent_id"] == order["broker_id"]
                and other["status"] not in TERMINAL
            ):
                other.update(status="Submitted", accepted_sequence=sequence)
                if order.get("group_id"):
                    other["stop"] = str(stop_after_fill)
            elif (
                other["broker_id"] != order["broker_id"]
                and order["oca_group"]
                and other["oca_group"] == order["oca_group"]
                and other["status"] not in TERMINAL
            ):
                if self._is_entry(other):
                    self._cancel_group_entry(other)
                else:
                    other["status"] = "Cancelled"
        self._save("simulation.fill", execution)
        self.data.emit("execution", **execution)
        self._emit_orders()

    def account_values(self):
        gross, net, unrealized, marked = Decimal(0), Decimal(0), Decimal(0), True
        for position in self.state["positions"].values():
            quantity = number(position["quantity"])
            if not quantity:
                continue
            quote = self.quotes.get(position["conid"], {}).get("bid" if quantity > 0 else "ask")
            fresh = (
                quote
                and self.live.get(position["conid"])
                and (datetime.now(UTC) - datetime.fromisoformat(quote["at"])).total_seconds() <= 15
            )
            marked = marked and bool(fresh)
            price = quote["price"] if quote else number(position["average"])
            gross += abs(quantity) * price
            net += quantity * price
            unrealized += quantity * (price - number(position["average"]))
        equity = number(self.state["cash"]) + net
        if marked and self.state["baseline_day"] != now()[:10]:
            self.state.update(baseline_day=now()[:10], baseline_equity=str(equity))
            self._save("simulation.pnl.baseline", {"day": now()[:10], "equity": str(equity)})
        return (
            {
                "NetLiquidation": str(equity),
                "AvailableFunds": str(max(Decimal(0), equity - gross)),
                "GrossPositionValue": str(gross),
            },
            str(equity - number(self.state["baseline_equity"])) if marked else None,
            str(unrealized),
        )

    def reconcile(self):
        # Atomic simulator absence is proof that dispatch never reached this local
        # adapter. This conclusion is never used for an IBKR order.
        for intent in self.store.orders():
            if str(intent["broker_id"]) in self.state["orders"] or intent["state"] not in {
                "unknown",
                "reserved",
                "dispatching",
            }:
                continue
            payload = {**intent["payload"], **{k: intent[k] for k in ("id", "broker_id")}}
            if is_pair(payload):
                for leg in pair_legs(payload).values():
                    order = self._order(
                        payload,
                        leg["broker_id"],
                        leg["action"],
                        "STP",
                        price=leg["stop"],
                        status="Cancelled",
                    )
                    order.update(leg)
                    self.state["orders"][str(leg["broker_id"])] = order
                self._save("simulation.dispatch.not_accepted", {"id": intent["id"]})
                continue
            purpose = payload.get("purpose", "entry")
            order = self._order(
                payload,
                intent["broker_id"],
                payload.get("action", "BUY" if purpose == "entry" else "SELL"),
                "STP" if purpose == "protection" else "LMT",
                price=payload.get("stop") if purpose == "protection" else payload.get("limit"),
                status="Cancelled",
            )
            if purpose != "entry":
                order.update(
                    purpose=purpose,
                    oca_group="oms-" + payload.get("exit_group", payload["entry_id"]),
                    oca_type=2,
                    tif="GTC" if purpose == "protection" else "DAY",
                )
                if payload.get("pair_recovery"):
                    order["group_id"] = payload["entry_id"]
            self.state["orders"][str(order["broker_id"])] = order
            if purpose == "entry":
                for offset, kind, field in ((1, "LMT", "target"), (2, "STP", "stop")):
                    if payload.get(field):
                        child = self._order(
                            payload,
                            intent["broker_id"] + offset,
                            "SELL",
                            kind,
                            parent=intent["broker_id"],
                            price=payload[field],
                            status="Cancelled",
                        )
                        self.state["orders"][str(child["broker_id"])] = child
            self._save("simulation.dispatch.not_accepted", {"id": intent["id"]})
        for position in self.state["positions"].values():
            self.data.emit("position", **position)
        self._emit_orders()
        for execution in self.state["executions"]:
            self.data.emit("execution", **execution)
        facts, daily, unrealized = self.account_values()
        for tag, value in facts.items():
            self.data.emit("account_fact", tag=tag, value=value)
        self.data.emit(
            "daily_pnl",
            daily=daily if daily is not None else "NaN",
            unrealized=unrealized,
            realized="0",
        )
        for kind in (
            "positions_end",
            "orders_end",
            "completed_orders_end",
            "executions_end",
            "account_end",
        ):
            self.data.emit(kind)
