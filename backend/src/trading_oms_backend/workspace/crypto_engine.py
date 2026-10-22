"""Durable local triggers with broker-confirmed, paper-only crypto executions."""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from .contracts import execution_reason
from .graph import number
from .oca import protection_price, rounded
from .oca_engine import fresh
from .store import Conflict, now

TERMINAL_STATES = {"filled", "cancelled", "rejected"}


class CryptoPaperController:
    def _crypto_ceiling(self, run, profile):
        settings = run["binding"]["sizing"]
        qualified = (self.store.get("qualification", "crypto_paper") or {}).get("completed")
        return min(
            number(settings["notional"]),
            number(profile["notional"]),
            number(settings["risk"]) * 100,
            number(profile["planned_stop_risk"]) * 100,
            Decimal(1000 if qualified else 25),
        )

    def _crypto_orders(self):
        return [
            o for o in self.store.orders() if o["payload"].get("execution") == "crypto_breakout"
        ]

    def _crypto_candidate(self, run, state, context, capture, namespace="crypto"):
        if not context["bar_closed"] or not run.get("armed") or not state["market"].closed:
            return
        candle = state["market"].closed[-1]
        since = max(
            run["authorized_at"],
            run.get("live_after", run["authorized_at"]),
            state.get("oca_live_since", run["authorized_at"]),
        )
        if candle.start < datetime.fromisoformat(since) or run["entries"]:
            return
        old = self.store.get(namespace + "_trigger", run["id"]) or {}
        if (
            old.get("candle") == candle.start.isoformat()
            and old.get("authorization_id") == run["authorization_id"]
        ):
            return
        candidate = {
            "run_id": run["id"],
            "candle": candle.start.isoformat(),
            "expires_at": (candle.start + timedelta(minutes=2)).isoformat(),
            "authorization_id": run["authorization_id"],
            "capture": capture,
            "state": "skipped",
        }
        try:
            rules = self.market_rules.get(self.contracts[run["conid"]].get("market_rule"), [])
            high = rounded(candle.high, rules, True)
            last = self.data.get(run["conid"], {})
            if (
                not 0 < candle.low < candle.high
                or not fresh(last)
                or number(last.get("price", 0)) >= high
            ):
                raise Conflict("Invalid candle or Last already reached its high.")
            protection_price(high, "long", rules)
            candidate.update(
                high=str(high),
                state="monitoring",
                started_at=now(),
                after_sequence=last.get("sequence"),
            )
        except ValueError as exc:
            candidate["reason"] = str(exc)
        with self.store.transaction() as db:
            self.store.write(db, namespace + "_trigger", run["id"], candidate)
            self.store.append(db, "strategy." + namespace + ".candle", candidate)

    def _crypto_fresh(self, conid):
        data = self.data.get(conid, {})
        quotes = self.quotes.get(conid, {})
        return bool(
            data.get("live")
            and fresh(data)
            and fresh(data, "source_at")
            and all(
                fresh(quotes.get(side, {})) and number(quotes[side].get("price", 0)) > 0
                for side in ("bid", "ask")
            )
        )

    def _crypto_trade(self, event):
        if not self.connected or not self.attested or not self.position_agreement:
            return
        if abs(time.time() - event["timestamp"]) > 15:
            return
        for run in self.store.list("run"):
            if run.get("execution") != "crypto_breakout" or run["conid"] != event["conid"]:
                continue
            position = self.owned().get(run["id"])
            plan = self.store.get("crypto_protection", run["id"]) or {}
            if position and position["quantity"] > 0:
                if self._crypto_valid_protection(position) and number(event["price"]) <= number(
                    plan["stop"]
                ):
                    self._request_exit(run["id"])
                continue
            trigger = self.store.get("crypto_trigger", run["id"]) or {}
            if not (
                run.get("armed")
                and not run["entries"]
                and trigger.get("state") == "monitoring"
                and trigger.get("authorization_id") == run.get("authorization_id")
                and trigger["expires_at"] > now()
            ):
                continue
            if event.get("sequence") is not None and event.get("sequence") == trigger.get(
                "after_sequence"
            ):
                continue
            if datetime.fromtimestamp(event["timestamp"], UTC) < datetime.fromisoformat(
                trigger["started_at"]
            ):
                continue
            if number(event["price"]) >= number(trigger["high"]):
                if not self._crypto_fresh(run["conid"]):
                    trigger.update(
                        state="skipped",
                        reason="Crossing skipped: fresh Last, bid and ask are required.",
                    )
                    self.store.put("crypto_trigger", run["id"], trigger)
                    self.store.event("strategy.crypto.skipped", trigger)
                    continue
                # Latch before dispatch; neither duplicate ticks nor reconnects may resubmit.
                trigger.update(state="triggered", triggered_at=now())
                self.store.put("crypto_trigger", run["id"], trigger)
                self.store.event("strategy.crypto.triggered", trigger)
                try:
                    self._crypto_enter(run, trigger)
                except ValueError as exc:
                    self.disarm(run["id"], str(exc))
                    self.store.event("risk.blocked", {"run_id": run["id"], "reason": str(exc)})

    def _crypto_enter(self, run, trigger):
        if not self._binding_valid(run):
            raise Conflict("Contract identity changed. Prepare and approve a new run binding.")
        document = self.store.version(run["strategy_id"], run["version"])["document"]
        contract = self.contracts[run["conid"]]
        if execution_reason(contract, document) or self.environment.crypto:
            raise Conflict("This contract/template requires the IBKR paper crypto adapter.")
        if (
            not all(c["passed"] for c in self.readiness([run]))
            or not self._crypto_fresh(run["conid"])
            or not self.data[run["conid"]].get("warm")
        ):
            raise Conflict("Fresh data, account funds, approval and reconciliation are required.")
        if not run.get("armed") or run["expires_at"] <= now() or run["entries"]:
            raise Conflict("Fresh authorization for one trade is required.")
        if datetime.now(UTC) >= datetime.fromisoformat(run["expires_at"]) - timedelta(minutes=15):
            raise Conflict("The entry session has ended.")
        if any(
            o["run_id"] == run["id"] and o["state"] not in TERMINAL_STATES
            for o in self.store.orders()
        ):
            raise Conflict("An earlier order outcome is unresolved.")
        for position in self.owned().values():
            if position["quantity"] and not fresh(self.data.get(position["conid"], {})):
                raise Conflict("Current position marks are required.")
        profile = run["limits"]
        qualified = (self.store.get("qualification", "crypto_paper") or {}).get("completed", False)
        reserved = sum(
            (number(r["notional"]) for r in self.store.list("reservation") if r.get("active")),
            Decimal(0),
        )
        budget = min(
            self._crypto_ceiling(run, profile),
            number(self.facts["AvailableFunds"]) - reserved,
            Decimal(5000) - number(self.facts["GrossPositionValue"]) - reserved,
        )
        budget = budget.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        increment, minimum = (
            number(contract.get("size_increment", 0)),
            number(contract.get("min_size", 0)),
        )
        ask = number(self.quotes[run["conid"]]["ask"]["price"])
        if increment <= 0 or minimum <= 0 or budget <= 0 or budget / ask < minimum:
            raise Conflict(
                "The reviewed cash budget is below the qualified minimum or funds are "
                "unavailable. It will not be increased automatically."
            )
        rules = self.market_rules.get(contract.get("market_rule"), [])
        stop = protection_price(ask, "long", rules)
        key = uuid.uuid4().hex
        payload = {
            "execution": "crypto_breakout",
            "purpose": "entry",
            "conid": run["conid"],
            "symbol": run["symbol"],
            "cash_quantity": str(budget),
            "quantity": "0",
            "protection_type": "locally_monitored",
            "stop": str(stop),
            "stop_ratio": "0.99",
            "price_rules": rules,
            "size_increment": str(increment),
            "capture": trigger["capture"],
            "candle": trigger["candle"],
            "binding_hash": run["binding"]["hash"],
            "authorization_id": run["authorization_id"],
        }
        reservation = {
            "symbol": run["symbol"],
            "conid": run["conid"],
            "risk": str(budget / 100),
            "notional": str(budget),
        }
        reserved_order = self.store.reserve_order(
            key, payload, run["id"], self.next_id, reservation
        )
        self.store.event(
            "crypto.risk.checked",
            {
                "run_id": run["id"],
                "budget": str(budget),
                "qualification_ceiling": "1000" if qualified else "25",
                "binding_hash": run["binding"]["hash"],
            },
        )
        run.update(entries=run["entries"] + 1, state="entry_working", blocking_reason=None)
        self.store.put("run", run["id"], run)
        self._crypto_dispatch(key, {**payload, **reserved_order})

    def _crypto_dispatch(self, key, intent):
        if intent.get("purpose", "entry") == "entry" and not self.guard_entry_dispatch(key):
            return
        self.store.mark_dispatch(key)
        try:
            self.broker.submit_crypto(intent)
        except Exception:
            self.store.transition(key, "unknown", {"reason": "dispatch_interrupted"})
            self.incident(
                "crypto_dispatch_uncertain",
                "A crypto paper order has an uncertain outcome. Reconcile before another attempt.",
            )
        self.reconciled = self.position_agreement = False
        self.next_reconcile = time.monotonic() + 1

    def _crypto_sync(self):
        orders = self._crypto_orders()
        if not orders:
            return
        with self.store.connect() as db:
            events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM executions")]
        corrected = {}
        for event in events:
            parts = event["execution_id"].rsplit(".", 1)
            group, revision = (
                (parts[0], int(parts[1]))
                if len(parts) == 2 and parts[1].isdigit()
                else (event["execution_id"], 0)
            )
            if group not in corrected or revision > corrected[group][0]:
                corrected[group] = revision, event
        for entry in orders:
            if entry["payload"]["purpose"] != "entry":
                continue
            fills = [
                e
                for _, e in corrected.values()
                if e["broker_id"] == entry["broker_id"] and e["side"] == "BOT"
            ]
            quantity = sum((number(e["quantity"]) for e in fills), Decimal(0))
            if not quantity:
                continue
            cost = sum(number(e["quantity"]) * number(e["price"]) for e in fills)
            average = cost / quantity
            try:
                stop = protection_price(average, "long", entry["payload"]["price_rules"])
            except ValueError:
                self.incident(
                    "crypto_stop_invalid",
                    (
                        "The crypto fill has no valid 1% stop increment. Inspect and close "
                        "the paper position manually."
                    ),
                )
                continue
            position = self.owned().get(entry["run_id"], {})
            if position.get("entry_id") != entry["id"]:
                continue
            if position.get("quantity", 0) < 0:
                self.incident(
                    "crypto_negative_position",
                    "Broker executions imply a negative crypto position. Inspect paper TWS; "
                    "all further entries are blocked.",
                )
            plan = {
                "run_id": entry["run_id"],
                "entry_id": entry["id"],
                "quantity": str(position.get("quantity", 0)),
                "average": str(average),
                "stop": str(stop),
                "type": "locally_monitored",
                "filled_quantity": str(quantity),
            }
            prior = self.store.get("crypto_protection", entry["run_id"])
            if plan != prior:
                with self.store.transaction() as db:
                    self.store.write(db, "crypto_protection", entry["run_id"], plan)
                    self.store.append(db, "crypto.protection.updated", plan)
            if cost > number(entry["payload"]["cash_quantity"]):
                self.incident(
                    "crypto_budget_exceeded",
                    (
                        "Broker crypto fills exceeded the submitted cash budget. New entries "
                        "are blocked."
                    ),
                )

    def _crypto_valid_protection(self, position):
        plan = self.store.get("crypto_protection", position["run_id"]) or {}
        return bool(
            self.connected
            and self.attested
            and self.position_agreement
            and self._crypto_fresh(position["conid"])
            and plan.get("entry_id") == position["entry_id"]
            and number(plan.get("quantity", 0)) == position["quantity"] > 0
            and number(plan.get("stop", 0)) > 0
        )

    def _crypto_close(self, key):
        self.store.put("exit_request", key, {"requested_at": now()})
        position = self.owned().get(key)
        if not position or position["quantity"] <= 0:
            raise Conflict("A confirmed owned long crypto position is required.")
        if (
            not self.position_agreement
            or not self.attested
            or not self.connected
            or time.monotonic() - self.reconciled_at >= 30
        ):
            raise Conflict("The exit request is saved. Reconcile ownership before sending it.")
        if self._identity_issues() or self._fill_agreement_issues():
            raise Conflict(
                "The exit request is saved; broker order identity or fills are unresolved."
            )
        if not self._crypto_fresh(position["conid"]):
            raise Conflict("The exit request is saved; fresh market data is required.")
        if any(o["state"] in {"unknown", "dispatching"} for o in self.store.orders()):
            raise Conflict("The exit request is saved; an order outcome remains uncertain.")
        related = [o for o in self._crypto_orders() if o["run_id"] == key]
        if any(o["state"] not in TERMINAL_STATES for o in related):
            return {"state": "exit_pending"}
        entry = next(o for o in related if o["id"] == position["entry_id"])
        increment = number(entry["payload"]["size_increment"])
        quantity = (position["quantity"] / increment).to_integral_value(
            rounding=ROUND_DOWN
        ) * increment
        if quantity != position["quantity"] or quantity <= 0:
            self.incident(
                "crypto_quantity_invalid",
                (
                    "The remaining crypto quantity is not a valid increment. Inspect the "
                    "paper account."
                ),
            )
            raise Conflict("The remaining crypto quantity requires operator review.")
        # Do not spin on a rejected exit: a fresh explicit review is needed.
        if any(
            o["payload"]["purpose"] == "exit"
            and (o["state"] == "rejected" or self.order_diagnostics(o).get("rejection"))
            for o in related
        ):
            raise Conflict("A crypto exit was rejected. Inspect broker capability before retrying.")
        identity = uuid.uuid4().hex
        payload = {
            "execution": "crypto_breakout",
            "purpose": "exit",
            "entry_id": entry["id"],
            "conid": position["conid"],
            "symbol": position["symbol"],
            "quantity": str(quantity),
            "action": "SELL",
            "protection_type": "locally_monitored",
        }
        reserved = self.store.reserve_order(identity, payload, key, self.next_id)
        self.store.event(
            "exit.risk_checked",
            {
                "run_id": key,
                "quantity": str(quantity),
                "reconciled_owned_quantity": str(position["quantity"]),
                "serialized": True,
            },
        )
        self._crypto_dispatch(identity, {**payload, **reserved})
        return {"state": "exit_pending"}

    def _crypto_reconciled(self):
        if not self.reconciled:
            return
        for order in self._crypto_orders():
            if order["payload"]["purpose"] != "entry" or order["state"] not in TERMINAL_STATES:
                continue
            key = order["run_id"]
            current = self.store.get("run", key) or {}
            if current.get("authorization_id") != order["payload"].get("authorization_id"):
                continue
            position = self.owned().get(key)
            trial = self.store.get("crypto_trial", order["id"]) or {}
            if (
                position
                and position["entry_id"] == order["id"]
                and position["quantity"] > 0
                and self._crypto_valid_protection(position)
            ):
                trial["protection_observed"] = True
                self.store.put("crypto_trial", order["id"], trial)
            elif not position or position["quantity"] == 0:
                run = self.store.get("run", key)
                outcome = (
                    "Trade completed; manually review and arm again."
                    if trial
                    else self._crypto_no_fill_reason(order)
                )
                if run and (run.get("armed") or run.get("state") != "paused"):
                    self.disarm(key, outcome)
                elif (
                    run
                    and not trial
                    and self.order_diagnostics(order).get("rejection")
                    and run.get("blocking_reason") != outcome
                ):
                    # Refine the initial uncertainty message without another disarm,
                    # cancellation request, authorization change, or incident release.
                    with self.store.transaction() as db:
                        run["blocking_reason"] = outcome
                        self.store.write(db, "run", key, run)
                        self.store.append(
                            db,
                            "run.entry_outcome",
                            {"run_id": key, "order_id": order["id"], "detail": outcome},
                        )
                    self._overview_cache = None
                if trial.get("protection_observed") and not trial.get("complete"):
                    trial["complete"] = True
                    self.store.put("crypto_trial", order["id"], trial)
                    self.store.put(
                        "qualification",
                        "crypto_paper",
                        {"completed": True, "entry_id": order["id"], "timestamp": now()},
                    )
                    self.store.event("crypto.paper.qualified", {"entry_id": order["id"]})

    def _crypto_maintain(self):
        for trigger in self.store.list("crypto_trigger"):
            if trigger.get("state") == "monitoring" and trigger["expires_at"] <= now():
                trigger["state"] = "expired"
                self.store.put("crypto_trigger", trigger["run_id"], trigger)
                self.store.event("strategy.crypto.expired", trigger)

    def _crypto_no_fill_reason(self, order):
        detail = self.order_diagnostics(order)
        if detail.get("rejection"):
            return (
                f"{detail['status_label']}. {detail['rejection']['detail']} "
                "Review and manually arm again."
            )
        cause = detail["cancellation_detail"]
        if cause:
            return f"Entry ended without a fill. {cause}. Review and manually arm again."
        if order["state"] == "rejected":
            return (
                "Broker rejected the entry without a fill. "
                "Inspect order diagnostics before re-arming."
            )
        return (
            "Broker confirmed the entry ended without a fill. "
            "Review order details before re-arming."
        )

    def _crypto_identity_status(self, intent, observed):
        p = intent["payload"]
        entry = p["purpose"] == "entry"
        expected = {
            "client_id": self.broker.client_id,
            "own_account": True,
            "reference": "oms-" + intent["id"],
            "conid": p["conid"],
            "order_type": "MKT",
            "tif": "IOC",
            "action": "BUY" if entry else "SELL",
            "parent_id": 0,
        }
        if any(observed[k] != v for k, v in expected.items() if observed.get(k) is not None):
            return "mismatch"
        amount = "cash_quantity" if entry else "quantity"
        if observed.get(amount) is not None:
            try:
                if number(observed[amount]) != number(p[amount]):
                    return "mismatch"
            except ValueError:
                return "mismatch"
        if any(observed.get(k) is None for k in (*expected, amount)):
            return "pending"
        return "verified"

    def _crypto_identity_issues(self, intent, observed):
        return {
            "verified": [],
            "pending": ["Awaiting complete broker order details."],
            "mismatch": ["Crypto broker order differs from its durable paper intent."],
        }[self._crypto_identity_status(intent, observed)]
