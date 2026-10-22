"""Acknowledgment-driven paired-entry lifecycle, isolated from legacy strategies."""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .graph import number
from .oca import is_pair, pair_legs, pair_prices, protection_price, size_pair
from .protection import ACTIVE, TERMINAL, order_ids
from .store import Conflict, now


def fresh(value, field="received_at", seconds=15):
    try:
        return (
            0
            <= (datetime.now(UTC) - datetime.fromisoformat(value[field])).total_seconds()
            <= seconds
        )
    except (KeyError, TypeError, ValueError):
        return False


class OCAController:
    def _paired_run(self, run):
        document = self.store.version(run["strategy_id"], run["version"])["document"]
        return any(n["kind"] == "paired_stop" for n in document["nodes"])

    def _pair_intent(self, order):
        return {**order["payload"], "id": order["id"], "broker_id": order["broker_id"]}

    def _oca_groups(self, run_id=None):
        return [g for g in self.store.list("oca_group") if run_id is None or g["run_id"] == run_id]

    def _oca_observed(self, broker_id):
        return (
            self.broker_orders.get(broker_id)
            or self.store.get("broker_order", str(broker_id))
            or {}
        )

    def _oca_record(self, group, kind, **changes):
        changed = any(group.get(k) != v for k, v in changes.items())
        if changed:
            group.update(changes)
            with self.store.transaction() as db:
                self.store.write(db, "oca_group", group["id"], group)
                self.store.append(
                    db, kind, {"id": group["id"], "run_id": group["run_id"], **changes}
                )

    def _oca_candidate(self, run, state, context, capture):
        if not context["bar_closed"] or not run.get("armed") or not state["market"].closed:
            return
        candle = state["market"].closed[-1]
        if self._stock_run(run) and not state["market"].live_candle_eligible(
            candle, datetime.now(UTC)
        ):
            return
        # A minute starting before authorization or recovery may contain historical/partial data.
        live_since = max(run["authorized_at"], state.get("oca_live_since", run["authorized_at"]))
        if candle.start < datetime.fromisoformat(live_since):
            return
        candidate = {
            "candle": candle.start.isoformat(),
            "high": str(candle.high),
            "low": str(candle.low),
            "capture": capture,
            "expires_at": (candle.start + timedelta(minutes=2)).isoformat(),
            "authorization_id": run["authorization_id"],
        }
        if self.store.get("oca_candidate", run["id"]) != candidate:
            self.store.put("oca_candidate", run["id"], candidate)
            self.store.event("strategy.oca.candle", {"run_id": run["id"], **candidate})
        self._oca_maintain()

    def _oca_levels(self, run, candidate, profile=None):
        settings = self._runtime(run)["graph"].document["settings"]
        contract = self.contracts.get(run["conid"], {})
        rules = self.market_rules.get(contract.get("market_rule"), [])
        prices = pair_prices(number(candidate["high"]), number(candidate["low"]), rules)
        reserved = sum(
            (number(r["notional"]) for r in self.store.list("reservation") if r.get("active")),
            Decimal(0),
        )
        if self._stock_run(run):
            quantity, reservation = self._stock_size(
                run,
                [
                    (number(prices[s + "_entry"]), number(prices[s + "_stop"]))
                    for s in ("long", "short")
                ],
                profile,
            )
            return prices, quantity, reservation, rules
        quantity, reservation = size_pair(
            settings,
            profile or run["limits"],
            prices,
            number(self.facts.get("AvailableFunds", 0)) - reserved,
            contract,
        )
        reservation["conid"] = run["conid"]
        return prices, quantity, reservation, rules

    def _oca_preview(self, run, profile):
        market = self._runtime(run)["market"]
        summary = {
            "run_id": run["id"],
            "kind": "oca_breakout",
            "stop_percent": "1",
            "refresh": "Each completed minute, after confirmed cancellation",
            "completion": "One trade then pause",
            "status": "Waiting for a completed candle",
            "hypothetical_short": self.environment.crypto,
        }
        if market.closed:
            candle = market.closed[-1]
            candidate = {
                "candle": candle.start.isoformat(),
                "high": str(candle.high),
                "low": str(candle.low),
            }
            try:
                prices, quantity, reservation, _ = self._oca_levels(run, candidate, profile)
                summary.update(
                    candidate,
                    prices=prices,
                    quantity=str(quantity),
                    reservation=reservation,
                    status="Indicative only; execution waits for a new complete live minute",
                )
            except ValueError as exc:
                summary["status"] = str(exc)
        return summary

    def _oca_borrow_ready(self, conid, quantity):
        borrow = getattr(self, "shortable", {}).get(conid, {})
        available = fresh(borrow, seconds=60) and number(borrow.get("quantity", 0)) >= quantity
        if (
            not available
            and self.connected
            and self.attested
            and hasattr(self.broker, "refresh_shortable")
        ):
            if self.broker.refresh_shortable(conid):
                self.store.event("market.shortable.refresh", {"conid": conid})
        return available

    def _oca_can_expand(self):
        evidence = self.store.get("qualification", "oca_paper") or {}
        return all(evidence.get(side) for side in ("long", "short"))

    def _oca_provisional(self, position, order):
        group = self.store.get("oca_group", order["id"]) or {}
        if not group.get("winner"):
            return False
        observed = self._oca_observed(order["payload"]["leg_ids"][group["winner"] + "_stop"])
        amendment = self.store.get("oca_amendment", order["id"]) or {}
        return (
            observed.get("status") in ACTIVE
            and not self._oca_identity_issues(order, observed["broker_id"], observed)
            and number(observed.get("quantity", 0)) - number(observed.get("filled", 0))
            == abs(position["quantity"])
            and (not amendment or fresh(amendment, "requested_at", 10))
        )

    def _oca_submit(self, run, candidate):
        if hasattr(self, "_binding_valid") and not self._binding_valid(run):
            raise Conflict("Contract identity changed. Prepare and approve a new run binding.")
        if not all(c["passed"] for c in self.readiness([run])):
            raise Conflict("Connection, reconciliation, funds or incidents block paired entries.")
        bounds = self._runtime(run)["market"].session_bounds(datetime.now(UTC))
        if (
            not bounds
            or not bounds[0] <= datetime.now(UTC) < bounds[1] - timedelta(minutes=15)
            or run["expires_at"] <= now()
            or candidate["expires_at"] <= now()
        ):
            raise Conflict("The entry candle or session expired.")
        if any(
            g.get("counted") and g.get("authorization_id") == run["authorization_id"]
            for g in self._oca_groups(run["id"])
        ):
            raise Conflict("This authorization already opened its one trade. Re-arm after closing.")
        data = self.data.get(run["conid"], {})
        quotes = self.quotes.get(run["conid"], {})
        if (
            not data.get("warm")
            or not data.get("live")
            or not fresh(data)
            or not fresh(data, "source_at")
        ):
            raise Conflict("Fresh live Last and complete warm-up are required.")
        if any(not fresh(quotes.get(side, {})) for side in ("bid", "ask")):
            raise Conflict("Fresh bid and ask are required for paired entries.")
        prices, quantity, reservation, rules = self._oca_levels(run, candidate)
        if not number(prices["short_entry"]) < number(data["price"]) < number(prices["long_entry"]):
            candidate["skipped"] = "Price already reached a trigger before submission."
            self.store.put("oca_candidate", run["id"], candidate)
            raise Conflict(candidate["skipped"])
        if not 0 < number(quotes["bid"]["price"]) <= number(quotes["ask"]["price"]):
            raise Conflict("Bid and ask must be positive and uncrossed.")
        for position in self.owned().values():
            mark = self.data.get(position["conid"], {})
            if position["quantity"] and (not fresh(mark) or number(mark.get("price", 0)) <= 0):
                raise Conflict("Current position marks are unavailable.")
        if not self.environment.crypto:
            if run.get("unattended"):
                raise Conflict("Paired paper entries require a supervised session.")
            if not self._stock_run(run) and quantity > 1 and not self._oca_can_expand():
                raise Conflict("Complete one-share long and short OCA paper qualification first.")
            if not self._oca_borrow_ready(run["conid"], quantity):
                raise Conflict("Fresh sufficient shortable shares are required for the whole pair.")
            from .credit_policy import broker_credit

            credit_plan = (run.get("binding") or {}).get("execution_plan") or {}
            if broker_credit(credit_plan):
                # The bound funding policy assessed both branches in _oca_levels.
                # Broker-decision policies deliberately do not require a preview.
                preview = {"status": "accepted", "received_at": now()}
            else:
                preview = self.store.get("oca_credit", run["id"]) or {}
            preview_key = {
                "conid": run["conid"],
                "quantity": str(quantity),
                "price": prices["short_entry"],
                "candle": candidate["candle"],
                "epoch": self.broker.epoch,
            }
            if not broker_credit(credit_plan) and any(
                preview.get(k) != v for k, v in preview_key.items()
            ):
                if not self._claim_credit_slot():
                    raise Conflict(
                        "Waiting for account credit-preview pacing; no entries submitted."
                    )
                identity = self.store.allocate_broker_id(self.next_id)
                preview = {
                    **preview_key,
                    "broker_id": identity,
                    "status": "pending",
                    "received_at": now(),
                }
                self.store.put("oca_credit", run["id"], preview)
                self.store.event("oca.short_credit.requested", {"run_id": run["id"], **preview})
                self.broker.preview_short(
                    {
                        **preview,
                        **(self._stock_payload(run, reservation) if self._stock_run(run) else {}),
                    }
                )
                raise Conflict(
                    "Waiting for the broker short-sale credit preview; no entries submitted."
                )
            if preview.get("status") != "accepted" or not fresh(preview, seconds=60):
                raise Conflict(
                    "Broker short-sale credit preview is pending or rejected; pair blocked."
                )
        identity = uuid.uuid4().hex
        payload = {
            "purpose": "entry",
            "execution": "oca_breakout",
            "conid": run["conid"],
            "symbol": run["symbol"],
            "quantity": str(quantity),
            "prices": prices,
            "price_rules": rules,
            "candle": candidate["candle"],
            "timeout": 60,
            "expires_at": candidate["expires_at"],
            "capture": candidate["capture"],
            "quote_capture": self.store.capture({"source": "oca_quotes", "quotes": quotes}),
            "exit_groups": {side: uuid.uuid4().hex for side in ("long", "short")},
        }
        if self._stock_run(run):
            payload.update(self._stock_payload(run, reservation))
        reserved = self.store.reserve_order(identity, payload, run["id"], self.next_id, reservation)
        if not self.guard_entry_dispatch(identity):
            return
        self.store.mark_dispatch(identity)
        try:
            self.broker.submit_pair({**payload, **reserved})
        except Exception:
            self.store.transition(identity, "unknown", {"reason": "paired_dispatch_interrupted"})
            self.incident(
                "oca_dispatch_uncertain",
                "Paired dispatch is uncertain. Inspect the paper order structure; "
                "no fallback or resend.",
            )
        run = self.store.get("run", run["id"])
        run.update(last_signal=now())
        if run.get("armed"):
            run.update(state="entry_working", blocking_reason=None)
        self.store.put("run", run["id"], run)
        self.invalidate_reconciliation()
        self.next_reconcile = time.monotonic() + 1

    def _oca_cancel(self, order, reason):
        group = self.store.get("oca_group", order["id"])
        self._oca_record(group, "oca.cancel.requested", state="cancelling", cancel_reason=reason)
        # Only parent cancellation here. Children can be the sole protection for a late fill.
        for side in ("long", "short"):
            broker_id = order["payload"]["leg_ids"][side + "_entry"]
            if self._oca_observed(broker_id).get("status") not in TERMINAL:
                self._queue_cancel(broker_id, "oca_entry")
        self.invalidate_reconciliation()
        self.next_reconcile = min(self.next_reconcile, time.monotonic() + 1)

    def _oca_executions(self, order):
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT payload FROM executions WHERE order_id=? ORDER BY rowid", (order["id"],)
            ).fetchall()
        corrected = {}
        for row in rows:
            event = json.loads(row[0])
            parts = event["execution_id"].rsplit(".", 1)
            key, revision = (
                (parts[0], int(parts[1]))
                if len(parts) == 2 and parts[1].isdigit()
                else (event["execution_id"], 0)
            )
            if key not in corrected or revision > corrected[key][0]:
                corrected[key] = revision, event
        return [e for _, e in corrected.values()]

    def _oca_sync(self, order):
        group = self.store.get("oca_group", order["id"])
        ids = order["payload"]["leg_ids"]
        executions = self._oca_executions(order)
        sides = [
            side
            for side in ("long", "short")
            if any(
                e["broker_id"] == ids[side + "_entry"] and number(e["quantity"]) > 0
                for e in executions
            )
        ]
        if len(sides) > 1:
            self.incident(
                "oca_multiple_entries",
                "Both OCA entry branches executed. Disarm and reconcile the net "
                "holding and protection immediately.",
            )
            self.disarm(order["run_id"], "Both OCA branches executed; operator recovery required.")
            self._oca_record(group, "oca.overfill", state="uncertain")
            return
        if not sides:
            observations = [self._oca_observed(i) for i in ids.values()]
            if any(o.get("status") in {"Rejected", "Inactive"} for o in observations):
                self.incident(
                    "oca_structure_rejected",
                    "A paired entry or protection leg was rejected. Inspect Gateway; "
                    "the whole pair is blocked.",
                )
                self._oca_cancel(order, "paired_leg_rejected")
            if all(o.get("status") in TERMINAL for o in observations):
                if any(number(o.get("filled", 0)) for o in observations):
                    return  # Wait for the corresponding execution callbacks.
                self._oca_record(group, "oca.cancel.confirmed", state="cancelled")
                if order["state"] != "cancelled":
                    self.store.transition(order["id"], "cancelled", {"all_legs_terminal": True})
            elif group["state"] == "reserved" and all(
                o.get("status") in ACTIVE for o in observations
            ):
                self._oca_record(group, "oca.working", state="working")
                self.store.transition(order["id"], "working", {"all_legs_acknowledged": True})
            return
        side = sides[0]
        entries = [e for e in executions if e["broker_id"] == ids[side + "_entry"]]
        filled = sum((number(e["quantity"]) for e in entries), Decimal(0))
        average = (
            sum((number(e["quantity"]) * number(e["price"]) for e in entries), Decimal(0)) / filled
        )
        try:
            desired = protection_price(average, side, order["payload"]["price_rules"])
        except ValueError:
            # The broker fill already happened. Retain the staged protection and
            # request a risk-reducing close rather than abandoning cancellation.
            desired = number(order["payload"]["prices"][side + "_stop"])
            self.incident(
                "oca_stop_increment",
                "The actual fill cannot support a 1% stop at qualified increments. "
                "Prior protection is retained; a closing exit is requested.",
            )
            self.disarm(
                order["run_id"], "The fill price cannot support the approved protective distance."
            )
            self.store.put("exit_request", order["run_id"], {"requested_at": now()})
        self._oca_record(
            group,
            "oca.fill.selected",
            winner=side,
            average=str(average),
            stop=str(desired),
            filled=str(filled),
        )
        if not group.get("counted"):
            with self.store.transaction() as db:
                run = self.store.read(db, "run", order["run_id"])
                run.update(entries=run.get("entries", 0) + 1, last_fill_at=now())
                group["counted"] = True
                self.store.write(db, "run", run["id"], run)
                self.store.write(db, "oca_group", group["id"], group)
                self.store.append(
                    db,
                    "oca.trade.counted",
                    {"id": group["id"], "run_id": run["id"], "direction": side},
                )
        if order["state"] != "filled":
            self.store.transition(order["id"], "filled", {"winning_direction": side})
        # Cancel both parents (including the unfilled winning remainder), but retain
        # winning protection. Native OCA acknowledgments are still required.
        for direction in ("long", "short"):
            key = ids[direction + "_entry"]
            if self._oca_observed(key).get("status") not in TERMINAL:
                self._queue_cancel(key, "oca_first_fill")
        opposite = "short" if side == "long" else "long"
        orphan = ids[opposite + "_stop"]
        if self._oca_observed(orphan).get("status") in ACTIVE:
            self._queue_cancel(orphan, "oca_orphan_protection")
        position = self.owned().get(order["run_id"])
        if position and position["quantity"]:
            self._oca_record(group, "oca.position.open", state="position_open")
            if abs(position["quantity"]) > filled or (position["quantity"] > 0) != (side == "long"):
                self.incident(
                    "oca_position_direction",
                    "The OCA holding disagrees with its winning entry; reconcile before recovery.",
                )
                return
            self._oca_update_protection(position, order, group)
            run = self.store.get("run", order["run_id"])
            limits = run.get("limits", {})
            conversion = Decimal(1)
            if order["payload"].get("stock_plan"):
                conversion = number(
                    order["payload"]["stock_plan"]["rules"]["price_scale"]
                ) * number(order["payload"]["valuation"]["fx_rate"])
            from .paper_risk import effective

            sizing = (run.get("binding") or {}).get("sizing", {})
            cap = effective(limits.get("notional", "1000"), sizing.get("notional"))
            risk_cap = effective(limits.get("planned_stop_risk", "10"), sizing.get("risk"))
            if (cap is not None and abs(position["quantity"]) * average * conversion > cap) or (
                risk_cap is not None
                and abs(position["quantity"]) * abs(average - desired) * conversion > risk_cap
            ):
                self.incident(
                    "oca_fill_gap_limit",
                    "An entry gap exceeded the planned risk or notional cap. "
                    "Protection is retained and a closing exit is requested.",
                )
                self.disarm(run["id"], "Entry gap exceeded the approved budget.")
                self.store.put("exit_request", run["id"], {"requested_at": now()})

    def _oca_update_protection(self, position, order, group):
        broker_id = order["payload"]["leg_ids"][group["winner"] + "_stop"]
        repairs = [
            o
            for o in self.store.orders()
            if o["payload"].get("purpose") == "protection"
            and o["payload"].get("entry_id") == order["id"]
        ]
        repair = repairs[0] if repairs else None
        if repair:
            broker_id = repair["broker_id"]
        observed = self._oca_observed(broker_id)
        desired = {
            "broker_id": broker_id,
            "quantity": str(abs(position["quantity"])),
            "stop": group["stop"],
        }
        amendment = self.store.get("oca_amendment", order["id"]) or {}
        if (
            observed.get("status") in ACTIVE
            and number(observed.get("stop", 0)) == number(desired["stop"])
            and number(observed.get("quantity", 0)) - number(observed.get("filled", 0))
            == abs(position["quantity"])
        ):
            if amendment and amendment.get("state") != "acknowledged":
                amendment.update(state="acknowledged", acknowledged_at=now())
                self.store.put("oca_amendment", order["id"], amendment)
                self.store.event("oca.protection.acknowledged", {"id": order["id"], **desired})
            if group.get("protection") != "verified":
                self._oca_record(group, "oca.protection.observed", protection="acknowledged")
            return
        if amendment.get("state") == "pending":
            if not fresh(amendment, "requested_at", 10):
                self.incident(
                    "oca_protection_uncertain",
                    "The fill-based stop amendment is unconfirmed. Prior protection "
                    "is retained; inspect recovery.",
                )
            return
        if observed.get("status") in TERMINAL:
            self._oca_repair_stop(position, order, group, repair)
            return
        if (
            not self.connected
            or not self.attested
            or observed.get("status") not in ACTIVE
            or not self.position_agreement
        ):
            return
        amendment = {
            **desired,
            "state": "pending",
            "requested_at": now(),
            "previous_stop": observed.get("stop"),
        }
        with self.store.transaction() as db:
            self.store.write(db, "oca_amendment", order["id"], amendment)
            self.store.append(
                db,
                "oca.protection.amend.risk_checked",
                {"id": order["id"], "run_id": order["run_id"], **amendment},
            )
        self._oca_record(group, "oca.protection.pending", protection="amendment_pending")
        try:
            self.broker.amend_protection(self._pair_intent(repair or order), amendment)
        except Exception:
            self.incident(
                "oca_protection_uncertain",
                "The protective amendment failed or is uncertain. Inspect the "
                "retained stop and reconcile.",
            )
        self.invalidate_reconciliation()
        self.next_reconcile = time.monotonic() + 1

    def _oca_repair_stop(self, position, order, group, previous):
        if not self.position_agreement or not self.connected or not self.attested:
            return
        ids = order["payload"]["leg_ids"]
        # A broker may cancel its held child when a partially filled parent is
        # cancelled. Only a complete, matching snapshot permits a replacement.
        for broker_id in ids.values():
            if self._oca_observed(broker_id).get("status") not in TERMINAL:
                return
        related = [o for o in self.store.orders() if o["payload"].get("entry_id") == order["id"]]
        if any(self._oca_observed(o["broker_id"]).get("status") not in TERMINAL for o in related):
            return
        identity = uuid.uuid4().hex
        payload = {
            "purpose": "protection",
            "pair_recovery": True,
            "entry_id": order["id"],
            "conid": position["conid"],
            "symbol": position["symbol"],
            "quantity": str(abs(position["quantity"])),
            "stop": group["stop"],
            "action": "SELL" if position["quantity"] > 0 else "BUY",
            "exit_group": order["payload"]["exit_groups"][group["winner"]],
        }
        self.store.event(
            "oca.protection.repair.risk_checked",
            {
                "run_id": order["run_id"],
                "id": order["id"],
                "quantity": payload["quantity"],
                "prior_legs_terminal": True,
            },
        )
        if order["payload"].get("stock_plan"):
            payload["stock_plan"] = order["payload"]["stock_plan"]
        intent = self.store.reserve_order(identity, payload, order["run_id"], self.next_id)
        self.store.mark_dispatch(identity)
        self.store.put("oca_amendment", order["id"], {})
        try:
            self.broker.submit_protection({**payload, **intent})
        except Exception:
            self.store.transition(
                identity, "unknown", {"reason": "paired_protection_repair_interrupted"}
            )
            self.incident(
                "oca_protection_uncertain",
                "Replacement protection is uncertain; do not resend before reconciliation.",
            )
        self.invalidate_reconciliation()
        self.next_reconcile = time.monotonic() + 1

    def _oca_maintain(self):
        for order in self.store.orders():
            if not is_pair(order["payload"]):
                continue
            self._oca_sync(order)
            group = self.store.get("oca_group", order["id"])
            if group["state"] in {"cancelled", "complete", "uncertain"} or group.get("winner"):
                continue
            run = self.store.get("run", order["run_id"]) or {}
            data = self.data.get(order["payload"]["conid"], {})
            quotes = self.quotes.get(order["payload"]["conid"], {})
            if (
                not run.get("armed")
                or self.store.emergency()
                or order["payload"]["expires_at"] <= now()
                or not data.get("warm")
                or not data.get("live")
                or not fresh(data)
                or any(not fresh(quotes.get(side, {})) for side in ("bid", "ask"))
            ):
                if group["state"] != "cancelling":
                    self._oca_cancel(order, "expired_disarmed_or_stale")
        for run in self.store.list("run"):
            if not run.get("armed") or not self._paired_run(run):
                continue
            groups = self._oca_groups(run["id"])
            if any(g["state"] not in {"cancelled", "complete"} for g in groups):
                continue
            candidate = self.store.get("oca_candidate", run["id"])
            if (
                not candidate
                or candidate.get("skipped")
                or candidate["expires_at"] <= now()
                or candidate["authorization_id"] != run["authorization_id"]
                or any(g["candle"] == candidate["candle"] for g in groups)
            ):
                continue
            try:
                self._signal_detect(run, candidate, candidate["capture"])
                self._oca_submit(run, candidate)
            except ValueError as exc:
                from .credit import CreditPending

                self._signal_outcome(
                    run, "checking" if isinstance(exc, CreditPending) else "blocked", str(exc)
                )
                if run.get("blocking_reason") != str(exc):
                    run["blocking_reason"] = str(exc)
                    self.store.put("run", run["id"], run)
                    self.store.event("risk.blocked", {"run_id": run["id"], "reason": str(exc)})

    def _oca_identity_issues(self, order, broker_id, observed):
        legs = pair_legs(self._pair_intent(order))
        expected = next(leg for leg in legs.values() if leg["broker_id"] == broker_id)
        valid = (
            observed.get("client_id") == self.broker.client_id
            and observed.get("own_account") is True
            and observed.get("conid") == order["payload"]["conid"]
        )
        for field in (
            "action",
            "order_type",
            "parent_id",
            "tif",
            "oca_type",
            "oca_group",
            "reference",
        ):
            valid = valid and observed.get(field) == expected[field]
        quantities, stops = {number(expected["quantity"])}, {number(expected["stop"])}
        group = self.store.get("oca_group", order["id"]) or {}
        amendment = self.store.get("oca_amendment", order["id"]) or {}
        if expected["purpose"] == "protection" and group.get("winner") == expected["direction"]:
            if group.get("stop"):
                stops.add(number(group["stop"]))
            if amendment.get("broker_id") == broker_id:
                quantities.add(number(amendment["quantity"]))
                stops.add(number(amendment["stop"]))
                if amendment.get("previous_stop"):
                    stops.add(number(amendment["previous_stop"]))
        valid = (
            valid
            and number(observed.get("quantity", 0)) in quantities
            and number(observed.get("stop") or 0) in stops
        )
        return (
            [] if valid else ["Paired order identity or payload differs from its durable intent."]
        )

    def _oca_valid_protection(self, position, order):
        group = self.store.get("oca_group", order["id"]) or {}
        if not group.get("winner"):
            return False
        broker_id = order["payload"]["leg_ids"][group["winner"] + "_stop"]
        repairs = [
            o
            for o in self.store.orders()
            if o["payload"].get("purpose") == "protection"
            and o["payload"].get("entry_id") == order["id"]
        ]
        if repairs:
            broker_id = repairs[0]["broker_id"]
        observed = self._oca_observed(broker_id)
        identity_ok = (
            (not self._oca_identity_issues(order, broker_id, observed))
            if not repairs
            else (
                observed.get("client_id") == self.broker.client_id
                and observed.get("own_account") is True
                and observed.get("conid") == position["conid"]
                and observed.get("reference") == "oms-" + repairs[0]["id"]
                and observed.get("action") == ("SELL" if position["quantity"] > 0 else "BUY")
                and observed.get("oca_group")
                == "oms-" + order["payload"]["exit_groups"][group["winner"]]
                and observed.get("order_type") == "STP"
                and observed.get("oca_type") == 2
                and observed.get("tif") == "GTC"
            )
        )
        valid = (
            observed.get("status") in ACTIVE
            and identity_ok
            and number(observed.get("stop", 0)) == number(group["stop"])
            and number(observed.get("quantity", 0)) - number(observed.get("filled", 0))
            == abs(position["quantity"])
        )
        if valid:
            self._oca_record(
                group, "oca.protection.verified", protection="verified", protection_verified=True
            )
        return valid

    def _oca_reconciled(self):
        for order in self.store.orders():
            if not is_pair(order["payload"]):
                continue
            group = self.store.get("oca_group", order["id"])
            if group["state"] == "complete":
                continue
            position = self.owned().get(order["run_id"])
            related = {
                o["broker_id"]
                for o in self.store.orders()
                if o["payload"].get("entry_id") == order["id"]
            }
            all_terminal = all(
                self._oca_observed(i).get("status") in TERMINAL for i in order_ids(order) | related
            )
            if (
                group.get("winner")
                and (not position or not position["quantity"])
                and all_terminal
                and self.reconciled
            ):
                self._oca_record(group, "oca.trade.completed", state="complete")
                run = self.store.get("run", order["run_id"])
                if run.get("authorization_id") == group["authorization_id"] and run.get("armed"):
                    self.disarm(
                        run["id"],
                        "One OCA trade completed. Review and manually re-arm for another.",
                    )
                from .broker import PaperGateway

                with self.store.connect() as db:
                    had_incident = (
                        db.execute(
                            "SELECT 1 FROM events WHERE type='incident.raised' "
                            "AND timestamp>=? LIMIT 1",
                            (group["created_at"],),
                        ).fetchone()
                        is not None
                    )
                if (
                    type(self.broker) is PaperGateway
                    and group.get("protection_verified")
                    and not had_incident
                ):
                    evidence = self.store.get("qualification", "oca_paper") or {}
                    evidence[group["winner"]] = {"group_id": group["id"], "completed_at": now()}
                    self.store.put("qualification", "oca_paper", evidence)
