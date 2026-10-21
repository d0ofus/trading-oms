from __future__ import annotations

import copy
import json
import queue
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from .acceptance import observe_session
from .broker import PaperGateway
from .diagnostics import broker_diagnostic, exception_diagnostic
from .graph import GraphError, compile_graph, number
from .market import Market, calendar
from .oms import OrderLedger
from .operations import OperatorActions
from .paper_test import PaperConnectionTest
from .power import SleepGuard
from .protection import ProtectionController, order_ids
from .qualification import profiles, qualification_checks
from .runtime import evaluate_step, size_entry
from .store import Conflict, Store, now
from .verification import verified


def check(code, title, passed, detail, remedy="/settings"):
    return {
        "code": code,
        "title": title,
        "passed": bool(passed),
        "detail": detail,
        "remediation": remedy,
    }


class Engine(PaperConnectionTest, OperatorActions, ProtectionController, OrderLedger):
    """Single execution owner. HTTP and SDK threads never reduce trading state."""

    def __init__(self, store: Store, broker_factory=PaperGateway):
        self.store = store
        self.process_identity = uuid.uuid4().hex
        self._next_acceptance_record = 0.0
        self.observations = queue.Queue(maxsize=8192)
        self.commands = queue.Queue(maxsize=64)
        self.broker = broker_factory(self.observations)
        self.stopping = threading.Event()
        self.thread = None
        self.connected = self.attested = self.reconciled = False
        self.requested_connection = False
        self.heartbeat_at = self.reconciled_at = 0.0
        self.next_heartbeat = self.next_reconcile = self.next_connect = 0.0
        self.reconnect_delay = 1
        self.next_id = 0
        self.reconcile_parts = set()
        self.reconcile_inflight = False
        self.reconcile_deadline = 0.0
        self.positions, self.broker_orders, self.facts = {}, {}, {}
        self.contracts, self.quotes, self.data, self.runtime = {}, {}, {}, {}
        self.history_jobs, self.history_pending, self.history_bars = [], {}, {}
        self.buffered_ticks, self.repair_requests = {}, {}
        self.history_request_times = deque()
        self.next_history = 0.0
        self.last_fault = None
        self.server_version = None
        self.last_loop = time.monotonic()
        self._next_health_write = 0.0
        self._health_failed_at = None
        self.daily_pnl = None
        self.pnl_at = 0.0
        self._resume_attestation = False
        self.clock_ok = False
        self.market_rules = {}
        self.pending_subscriptions = set()
        self._next_runtime_clock = 0.0
        self.position_agreement = False
        self.code_verified = verified()
        self._recovered_context = False
        self.sleep_guard = SleepGuard()
        self._fault_at = time.monotonic()
        self._legacy_fault_restart = bool(store.get("incident", "engine_fault"))
        if type(self.broker) is PaperGateway and not store.get("migration", "flexible_sessions_v1"):
            from .recovery import backup_bundle

            if store.events(limit=1):
                backup = backup_bundle(store, store.directory / "backups")
                store.event("migration.backup.created", {"file": backup.name})
            store.put("migration", "flexible_sessions_v1", {"at": now(), "additive": True})
        profiles(store)
        self._restore()

    def _restore(self):
        self.store.verify()
        with self.store.transaction() as db:
            rows = db.execute("SELECT id,payload FROM documents WHERE kind='run'").fetchall()
            for row in rows:
                run = json.loads(row["payload"])
                if run.get("archived"):
                    continue
                run.update(
                    armed=False,
                    state="paused",
                    blocking_reason="Application restarted. Reconcile and re-arm for new entries.",
                )
                self.store.write(db, "run", row["id"], run)
            # A crash between intent persistence and the SDK call is deliberately
            # uncertain too. Absence from one broker snapshot is not proof of no order.
            db.execute(
                "UPDATE outbox SET state='unknown' WHERE state IN ('reserved','dispatching')"
            )
            self.store.append(db, "application.started", {"entries_disarmed": True})
        if any(
            o["state"] not in {"filled", "cancelled", "rejected"} for o in self.store.orders()
        ) or any(p["quantity"] > 0 for p in self.owned().values()):
            self.requested_connection = True

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="trading-engine", daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            try:
                self.call("shutdown")
            except (ValueError, TimeoutError):
                self.store.set_emergency(True)
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=8)
        self.broker.disconnect()

    def shutdown(self):
        for run in self.store.list("run"):
            self.disarm(run["id"], "Application is shutting down; fresh arming is required.")
        self.store.event(
            "application.stopping", {"entries_disarmed": True, "broker_protection_retained": True}
        )

    def call(self, method, **kwargs):
        if not self.thread:
            return getattr(self, method)(**kwargs)
        future = Future()
        try:
            self.commands.put_nowait((future, method, kwargs))
        except queue.Full as exc:
            raise Conflict("The engine is busy. Wait for pending actions to finish.") from exc
        try:
            return future.result(timeout=15)
        except TimeoutError as exc:
            cancelled = future.cancel()
            raise Conflict(
                "The queued action expired before it started."
                if cancelled
                else "This action is still pending. Inspect its current state before retrying."
            ) from exc

    def _loop(self):
        batch = []
        while not self.stopping.is_set():
            operation = "observe"
            try:
                # Preserve remaining callbacks when one reducer operation fails.
                # Never replay the failed observation: reconciliation establishes
                # its outcome before another risk-increasing decision is allowed.
                for _ in range(100 if not batch else 0):
                    try:
                        observation = self.observations.get_nowait()
                    except queue.Empty:
                        break
                    if observation.get("epoch") == self.broker.epoch:
                        batch.append(observation)
                ticks = [item for item in batch if item["type"] in {"tick", "quote"}]
                capture = self.store.capture_batch(ticks) if ticks else None
                self._batch_runs = self.store.list("run") if ticks else None
                while batch:
                    observation = batch.pop(0)
                    operation = "observe:" + observation["type"]
                    if observation["type"] in {"tick", "quote"}:
                        observation["capture"] = capture
                    self.observe(observation)
                    self._operation_succeeded(operation)
                self._batch_runs = None
                try:
                    future, method, kwargs = self.commands.get(timeout=0.025)
                except queue.Empty:
                    future = None
                if future is not None and future.set_running_or_notify_cancel():
                    try:
                        operation = method
                        future.set_result(getattr(self, method)(**kwargs))
                        self._operation_succeeded(method)
                    except (ValueError, KeyError) as exc:
                        future.set_exception(exc)
                    except Exception:
                        future.set_exception(
                            Conflict(
                                "The operation failed. Inspect Activity and recovery readiness."
                            )
                        )
                        raise
                operation = "maintain"
                self.maintain()
                self._operation_succeeded(operation)
                self.last_loop = time.monotonic()
            except Exception as exc:
                self.reconciled = False
                self._fault_at = time.monotonic()
                self.last_fault = (
                    "An engine operation failed. New entries are blocked; inspect recovery."
                )
                try:
                    self.incident(
                        "engine_fault",
                        self.last_fault,
                        diagnostic=exception_diagnostic(exc, operation),
                    )
                except Exception:
                    self.stopping.set()
        self.sleep_guard.set(False)

    def incident(self, code, detail, *, severity="critical", diagnostic=None):
        previous = self.store.get("incident", code)
        if previous and not previous.get("resolved"):
            previous.update(
                last_seen=now(),
                occurrences=previous.get("occurrences", 1) + 1,
                severity=severity,
                detail=detail,
                recovery={},
            )
            if diagnostic:
                previous["diagnostic"] = diagnostic
            self.store.put("incident", code, previous)
            return
        if not previous or previous.get("resolved"):
            item = {
                "id": code,
                "severity": severity,
                "detail": detail,
                "timestamp": now(),
                "resolved": False,
                "diagnostic": diagnostic or {},
                "occurrences": 1,
            }
            with self.store.transaction() as db:
                self.store.write(db, "incident", code, item)
                self.store.append(db, "incident.raised", item)
                if severity != "critical":
                    return
                notification_id = uuid.uuid4().hex
                self.store.write(
                    db,
                    "notification",
                    notification_id,
                    {
                        "id": notification_id,
                        "text": detail,
                        "state": "queued",
                        "created_at": now(),
                        "attempts": 0,
                    },
                )

    def connect(self):
        self.requested_connection = True
        self.next_connect = time.monotonic()
        self.store.event("connection.requested", {"endpoint": "localhost paper Gateway"})
        return {"state": "connecting"}

    def attest(self, confirmed):
        if confirmed is not True:
            raise ValueError("Confirm that Gateway displays a paper login before continuing.")
        self.broker.attest()
        self.attested = True
        self._restore_subscriptions()
        self.store.event("paper.context.attested", {"epoch": self.broker.epoch})
        self.begin_reconcile()
        return {"state": "reconciling"}

    def _restore_subscriptions(self):
        for run in self.store.list("run"):
            needs_monitoring = (
                run.get("armed")
                or self.owned().get(run["id"], {}).get("quantity", 0) > 0
                or any(
                    o["run_id"] == run["id"]
                    and o["state"] not in {"filled", "cancelled", "rejected"}
                    for o in self.store.orders()
                )
            )
            if needs_monitoring and run["conid"] not in self.contracts:
                self.broker.resolve(run["symbol"])
        self.pending_subscriptions.update(self.data)

    def _invalidate_authorizations(self, reason):
        # A changed account context must not send cancellations into the new account.
        with self.store.transaction() as db:
            for run in self.store.list("run"):
                run.update(armed=False, state="recovery_required", blocking_reason=reason)
                self.store.write(db, "run", run["id"], run)
            self.store.append(db, "authorization.invalidated", {"reason": reason})

    def _data_gap(self, conid, reason):
        data = self.data[conid]
        data.update(
            warm=False,
            repair_after=(
                datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1, seconds=2)
            ).isoformat(),
        )
        self.buffered_ticks[conid] = deque(maxlen=200000)
        self.store.event("market.gap", {"conid": conid, "reason": reason})

    def begin_reconcile(self):
        if not self.connected or not self.broker.paper_context:
            raise Conflict("Connect exactly one paper account before reconciliation.")
        if self.reconcile_inflight:
            return {"state": "reconciling"}
        self.reconcile_inflight = True
        self.reconcile_deadline = time.monotonic() + 30
        self.reconciled = False
        self.reconcile_parts = set()
        self.positions, self.broker_orders, self.facts = {}, {}, {}
        self.broker.reconcile()
        self.next_reconcile = time.monotonic() + 15
        self.store.event("reconciliation.started", {"epoch": self.broker.epoch})
        return {"state": "reconciling"}

    def resolve(self, symbol):
        request = self.broker.resolve(symbol.strip().upper())
        return {"request": request}

    def subscribe(self, conid):
        if conid not in self.contracts:
            raise ValueError("Select a broker-resolved symbol first.")
        if self.broker.subscribe(conid) is False:
            self.pending_subscriptions.add(conid)
        if conid not in self.data:
            self.data[conid] = {
                "conid": conid,
                "symbol": self.contracts[conid]["symbol"],
                "live": False,
                "received_at": None,
                "warm": False,
                "subscribed_at": now(),
                "history_loaded": False,
                "repair_after": (
                    datetime.now(UTC).replace(second=0, microsecond=0)
                    + timedelta(minutes=1, seconds=2)
                ).isoformat(),
            }
            self.buffered_ticks[conid] = deque(maxlen=200000)
            self._queue_history(conid)
        self.store.event("market.subscription.requested", {"conid": conid})
        return self.data[conid]

    def _queue_history(self, conid):
        # Eleven completed exchange sessions plus today's bars. Requests are
        # serialized and paced; they never generate entry decisions.
        cal = calendar()
        stamp = datetime.now(UTC)
        day = stamp.date().isoformat()
        sessions = cal.sessions_in_range((stamp - timedelta(days=24)).date().isoformat(), day)
        jobs = []
        for session in sessions[-12:]:
            from .sessions import candle_bounds

            end = min(candle_bounds(cal.session_open(session).to_pydatetime(), True)[1], stamp)
            jobs.append((conid, end.strftime("%Y%m%d-%H:%M:%S"), 60))
        jobs.append((conid, "", 5))
        self.history_jobs.extend(jobs)
        self.history_bars[conid] = {60: {}, 5: {}}

    def unsubscribe(self, conid):
        runs = [r for r in self.store.list("run") if r["conid"] == conid]
        ids = {r["id"] for r in runs}
        if (
            not self.reconciled
            or any(r.get("armed") or number(r.get("position", 0)) for r in runs)
            or any(
                o["run_id"] in ids and o["state"] not in {"filled", "cancelled", "rejected"}
                for o in self.store.orders()
            )
        ):
            raise Conflict("Disarm, close owned positions and reconcile before removing data.")
        self.broker.unsubscribe(conid)
        self.pending_subscriptions.discard(conid)
        self.history_jobs = [job for job in self.history_jobs if job[0] != conid]
        self.data.pop(conid, None)
        self.buffered_ticks.pop(conid, None)
        for run in runs:
            self.runtime.pop(run["id"], None)
        self.store.event("market.unsubscribed", {"conid": conid})
        return {"removed": True}

    def maintain(self):
        clock = time.monotonic()
        self._finish_removals()
        self._maintain_paper_tests()
        if self.reconcile_inflight and clock > self.reconcile_deadline:
            self._connection_lost("Reconciliation timed out; reconnecting for a fresh snapshot.")
            self.broker.disconnect()
        if type(self.broker) is PaperGateway and clock >= self._next_acceptance_record:
            self._next_acceptance_record = clock + 60
            observe_session(self)
        self._flush_cancellations()
        while self.history_request_times and clock - self.history_request_times[0] > 600:
            self.history_request_times.popleft()
        if clock >= self._next_health_write:
            import os

            self._next_health_write = clock + 2
            active_runs = self.store.list("run")
            self.sleep_guard.set(
                any(r.get("armed") or number(r.get("position", 0)) > 0 for r in active_runs)
            )
            if any(r.get("armed") and r.get("unattended") for r in active_runs):
                heartbeat = self.store.get("monitoring", "last_heartbeat") or {}
                notification_failed = any(
                    n.get("state") == "failed" for n in self.store.list("notification")
                )
                if (
                    notification_failed
                    or not heartbeat.get("passed")
                    or (
                        datetime.now(UTC)
                        - datetime.fromisoformat(
                            heartbeat.get("timestamp", "2000-01-01T00:00:00+00:00")
                        )
                    ).total_seconds()
                    > 90
                ):
                    self.incident(
                        "monitoring_unavailable",
                        "Unattended monitoring is unavailable. Entries are disarmed; "
                        "position protection is retained.",
                    )
                    for run in active_runs:
                        if run.get("armed") and run.get("unattended"):
                            self.disarm(run["id"], "Unattended monitoring failed.")
            from .health_file import publish_health

            published = publish_health(
                self.store.directory,
                {
                    "timestamp": time.time(),
                    "pid": os.getpid(),
                    "armed": any(r.get("armed") for r in self.store.list("run")),
                },
            )
            if published:
                self._health_failed_at = None
            else:
                self._health_failed_at = self._health_failed_at or clock
                self._next_health_write = clock + 0.25
                if clock - self._health_failed_at > 5:
                    raise OSError("Heartbeat publication failed beyond its bounded retry interval.")
        if self.broker.overflow.is_set():
            self.reconciled = False
            self.incident(
                "callback_overflow",
                "Broker observations overflowed. Reconnect and reconcile before new entries.",
            )
        if self.requested_connection and not self.connected and clock >= self.next_connect:
            self.next_connect = clock + self.reconnect_delay
            self.reconnect_delay = min(30, self.reconnect_delay * 2)
            try:
                self.broker.disconnect()
                self.broker.connect()
            except Exception:
                self.last_fault = (
                    "Gateway is unavailable or the pinned SDK is missing. Check Settings."
                )
        if self.connected and clock >= self.next_heartbeat:
            self.next_heartbeat = clock + 10
            self.broker.heartbeat()
        if self.connected:
            for conid in tuple(self.pending_subscriptions):
                if self.broker.subscribe(conid) is not False:
                    self.pending_subscriptions.discard(conid)
                    if not self.history_bars.get(conid):
                        self._queue_history(conid)
        for conid, data in self.data.items():
            from .sessions import candle_bounds

            data_window = candle_bounds(datetime.now(UTC), True)
            if (
                data_window
                and data_window[0] <= datetime.now(UTC) < data_window[1]
                and data.get("warm")
                and (
                    not data.get("received_at")
                    or (
                        datetime.now(UTC) - datetime.fromisoformat(data["received_at"])
                    ).total_seconds()
                    > 15
                )
            ):
                self._data_gap(conid, "Last-trade observations are stale.")
        if self.connected and self.heartbeat_at and clock - self.heartbeat_at > 30:
            self._connection_lost("Gateway heartbeat expired.")
            self.broker.disconnect()
        if self.connected and self.broker.paper_context and clock >= self.next_reconcile:
            self.begin_reconcile()
        if (
            self.connected
            and self.history_jobs
            and clock >= self.next_history
            and len(self.history_pending) < 2
            and len(self.history_request_times) < 55
        ):
            conid, end, seconds = self.history_jobs.pop(0)
            request = self.broker.history(conid, end, seconds)
            self.history_pending[request] = (clock, conid)
            self.history_request_times.append(clock)
            self.next_history = clock + 2.1
        for conid, data in self.data.items():
            if (
                self.connected
                and data.get("history_loaded")
                and not data.get("warm")
                and conid not in self.repair_requests.values()
                and data.get("repair_after", "z") <= now()
                and clock >= self.next_history
                and len(self.history_pending) < 2
                and len(self.history_request_times) < 60
            ):
                request = self.broker.history(conid, "", 60)
                self.history_pending[request] = (clock, conid)
                self.repair_requests[request] = conid
                self.history_request_times.append(clock)
                self.next_history = clock + 2.1
        for request, (since, conid) in list(self.history_pending.items()):
            if clock - since > 120:
                self.history_pending.pop(request)
                self.repair_requests.pop(request, None)
                if conid not in self.data:
                    continue
                self.data[conid]["repair_after"] = (
                    datetime.now(UTC) + timedelta(seconds=60)
                ).isoformat()
                # A timed-out initial request cannot count as a complete warm-up.
                self.data[conid]["history_failed"] = True
                if (
                    not self.data[conid].get("history_loaded")
                    and not any(j[0] == conid for j in self.history_jobs)
                    and not any(p[1] == conid for p in self.history_pending.values())
                ):
                    self.data[conid]["history_failed"] = False
                    self._queue_history(conid)
                self.incident(
                    "history_timeout",
                    "Historical data did not complete. Reconnect to repair the warm-up gap.",
                )
        for run in self.store.list("run"):
            if run.get("armed") and run["expires_at"] <= now():
                self.disarm(run["id"], "Session authorization expired.")
        if clock >= self._next_runtime_clock:
            self._next_runtime_clock = clock + 1
            self._clock_evaluations()
        for order in self.store.orders():
            if order["payload"].get("purpose") == "exit" and order["state"] == "working":
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(order["created_at"])
                ).total_seconds()
                if age > 10 and self.connected and self.attested:
                    self._cancel_known_sell(order["broker_id"])
                    self.store.transition(
                        order["id"], "cancel_pending", {"reason": "exit_limit_refresh"}
                    )
                    self.reconciled = False
                    self.next_reconcile = clock + 1
            if order["payload"].get("purpose", "entry") == "entry" and order["state"] in {
                "working",
                "dispatching",
            }:
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(order["created_at"])
                ).total_seconds()
                if age > order["payload"].get("timeout", 30) and self.attested and self.connected:
                    self.cancel_entry(order["id"])

    def _connection_lost(self, detail):
        self.reconcile_inflight = False
        self._resume_attestation = self._resume_attestation or self.attested
        self.connected = self.attested = self.reconciled = False
        self.clock_ok = False
        self.next_connect = time.monotonic() + 1
        for data in self.data.values():
            data["warm"] = False
            data["history_loaded"] = False
            data["live"] = False
            data["repair_after"] = (
                datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1, seconds=2)
            ).isoformat()
        self.history_jobs, self.history_pending, self.repair_requests = [], {}, {}
        self.history_bars = {}
        self.buffered_ticks = {conid: deque(maxlen=200000) for conid in self.data}
        self.store.event("connection.lost", {"detail": detail})
        for run in self.store.list("run"):
            if run.get("armed"):
                run.update(state="paused", blocking_reason=detail)
                self.store.put("run", run["id"], run)

    def observe(self, event):
        kind = event["type"]
        clock = time.monotonic()
        if kind == "handshake":
            self.connected = True
            self.next_id = max(self.next_id, event["next_id"])
            self.server_version = event["server_version"]
            self.heartbeat_at = clock
            self.reconnect_delay = 1
            self.last_fault = None
            self.store.event(
                "connection.handshake",
                {"epoch": self.broker.epoch, "server_version": self.server_version},
            )
        elif kind == "account_context":
            self.store.event(
                "paper.context.observed", {"paper": event["paper"], "count": event["count"]}
            )
            if not event["paper"] or event["count"] != 1:
                self.attested = self.reconciled = False
                self._invalidate_authorizations(
                    "Gateway login context changed. Fresh review is required."
                )
                self.incident(
                    "account_context",
                    "Gateway must have exactly one paper account. Account details are not stored.",
                )
            elif self._resume_attestation and self.broker.can_resume_attestation:
                self.broker.attest()
                self.attested = True
                self._resume_attestation = False
                self._recovered_context = True
                self._restore_subscriptions()
                self.begin_reconcile()
            elif (
                self._resume_attestation or self.attested
            ) and not self.broker.can_resume_attestation:
                self._resume_attestation = self.attested = self.reconciled = False
                self._invalidate_authorizations(
                    "Gateway login context changed. Fresh review is required."
                )
            elif self.connected:
                self._restore_subscriptions()
                self.begin_reconcile()
        elif kind == "heartbeat":
            self.heartbeat_at = clock
            self.clock_ok = abs(time.time() - event["timestamp"]) <= 5
            if not self.clock_ok:
                self.incident(
                    "clock_skew",
                    "Clock difference exceeds five seconds. Synchronize Windows time.",
                )
        elif kind == "disconnected":
            self._connection_lost("Gateway disconnected.")
        elif kind == "broker_error":
            code = event["code"]
            self.store.event("broker.message", {"code": code, "request": event["request"]})
            if code == 201 and any(event["request"] in order_ids(o) for o in self.store.orders()):
                rejected = {
                    "broker_id": event["request"],
                    "client_id": self.broker.client_id,
                    "status": "Rejected",
                    "rejection_code": 201,
                }
                self.broker_orders[event["request"]] = {
                    **self.broker_orders.get(event["request"], {}),
                    **rejected,
                }
                self._order_observation(rejected)
            if code in {1100, 1300, 502, 504}:
                self._connection_lost("Gateway connectivity interrupted.")
            elif code in {1101, 1102}:
                self.reconciled = False
                for conid in self.data:
                    self._data_gap(conid, "Gateway data recovery requires history repair.")
                if code == 1101:
                    self.broker.reset_subscriptions()
                    self.pending_subscriptions.update(self.data)
                if self.attested:
                    self.begin_reconcile()
            elif code in {2104, 2106}:
                previous = self.store.get("incident", "broker_2119")
                if previous and not previous.get("resolved"):
                    previous.update(
                        resolved=True,
                        severity="information",
                        recovery={"broker_code": code},
                        reviewed_at=now(),
                    )
                    self.store.put("incident", "broker_2119", previous)
                    self.store.event("incident.recovered", {"id": "broker_2119", "code": code})
            elif code not in {2107, 2108, 2158, 2109}:
                diagnostic = event.get("diagnostic") or broker_diagnostic(code)
                self.incident(
                    f"broker_{code}",
                    diagnostic["detail"],
                    severity="information" if code == 2119 else "critical",
                    diagnostic={**diagnostic, "request": event["request"]},
                )
        elif kind == "contract":
            self.contracts[event["conid"]] = {
                k: v for k, v in event.items() if k not in {"type", "epoch"}
            }
            if any(r["conid"] == event["conid"] for r in self.store.list("run")):
                self.subscribe(event["conid"])
        elif kind == "market_rule":
            self.market_rules[event["rule"]] = event["increments"]
        elif kind == "account_fact":
            self.facts[event["tag"]] = event["value"]
        elif kind == "daily_pnl":
            try:
                self.daily_pnl = number(event["daily"])
                self.pnl_at = clock
            except GraphError:
                self.daily_pnl = None
        elif kind == "position":
            if not event["own_account"]:
                self.incident(
                    "foreign_account", "Reconciliation observed an unexpected account context."
                )
            self.positions[event["conid"]] = event
        elif kind == "open_order":
            prior = self.store.get("broker_order", str(event["broker_id"])) or {}
            if event.get("status") == "Inactive" and prior.get("rejection_code") == 201:
                event["status"] = "Rejected"
            if event.get("completed") and event.get("reference", "").startswith("oms-"):
                intent = next(
                    (o for o in self.store.orders() if "oms-" + o["id"] == event["reference"]), None
                )
                if intent:
                    offset = 0
                    if (
                        intent["payload"].get("purpose", "entry") == "entry"
                        and event.get("action") == "SELL"
                    ):
                        offset = 2 if event.get("order_type") == "STP" else 1
                    event["broker_id"] = intent["broker_id"] + offset
            key = (
                event["broker_id"]
                if event["client_id"] == self.broker.client_id
                else f"external-{event['client_id']}-{event['broker_id']}"
            )
            self.broker_orders[key] = {**(self.store.get("broker_order", str(key)) or {}), **event}
            self._order_observation(event)
        elif kind == "order_status":
            prior = self.store.get("broker_order", str(event["broker_id"])) or {}
            if event.get("status") == "Inactive" and prior.get("rejection_code") == 201:
                event["status"] = "Rejected"
            key = (
                event["broker_id"]
                if event["client_id"] == self.broker.client_id
                else f"external-{event['client_id']}-{event['broker_id']}"
            )
            self.broker_orders[key] = {
                **self.broker_orders.get(key, {}),
                **event,
            }
            self._order_observation(event)
        elif kind == "execution":
            self._execution(event)
        elif kind == "commission":
            previous = self.store.get("commission", event["execution_id"])
            self.store.put(
                "commission",
                event["execution_id"],
                {**event, "received_at": (previous or {}).get("received_at", now())},
            )
            self.store.event("execution.commission", event)
        elif kind in {
            "positions_end",
            "orders_end",
            "completed_orders_end",
            "executions_end",
            "account_end",
        }:
            if not self.reconcile_inflight:
                return
            self.reconcile_parts.add(kind)
            if len(self.reconcile_parts) == 5:
                self._finish_reconcile()
        elif kind == "data_type" and event["conid"] in self.data:
            self.data[event["conid"]]["live"] = event["live"]
        elif kind == "quote":
            self.quotes.setdefault(event["conid"], {})[event["side"]] = {
                "price": event["price"],
                "received_at": now(),
                "capture": event.get("capture"),
            }
        elif kind == "historical_bar":
            bars = self.history_bars.get(event["conid"])
            if bars is not None:
                bars[event["seconds"]][event["timestamp"]] = event
        elif kind == "history_end":
            self.history_pending.pop(event["request"], None)
            repairing = self.repair_requests.pop(event["request"], None) is not None
            conid = event["conid"]
            if (
                conid in self.data
                and not any(job[0] == conid for job in self.history_jobs)
                and not any(p[1] == conid for p in self.history_pending.values())
            ):
                bars = self.history_bars[conid]
                manifest = self.store.capture(
                    {
                        "source": "ibkr_historical_candles",
                        "bars": {str(k): list(v.values()) for k, v in bars.items()},
                    }
                )
                if self.data[conid].get("history_failed") and not repairing:
                    self.data[conid]["history_failed"] = False
                    self._queue_history(conid)
                    return
                self.data[conid]["history_failed"] = False
                self.data[conid]["history_loaded"] = True
                self.data[conid]["capture"] = manifest
                if repairing:
                    ticks = self.buffered_ticks.get(conid, [])
                    completed = [int(key) + 60 for key in bars[60] if int(key) + 60 <= time.time()]
                    boundary = max(completed, default=0)
                    if not ticks or boundary < ticks[0]["timestamp"] or time.time() - boundary > 90:
                        self.data[conid]["repair_after"] = (
                            datetime.now(UTC) + timedelta(seconds=60)
                        ).isoformat()
                        return
                    self.data[conid]["warm"] = True
                    for run in self.store.list("run"):
                        if run.get("conid") == conid:
                            self._runtime(run, reset=True)
                    self.store.event(
                        "market.warmup.finished",
                        {"conid": conid, "capture": manifest, "retrospective_entries": False},
                    )
        elif kind == "tick":
            self._tick(event)

    def _finish_reconcile(self):
        self.reconcile_inflight = False
        identity_issues = self._identity_issues()
        identity_issues.extend(self._fill_agreement_issues())
        issues = list(identity_issues)
        owned = self.owned()
        self._reconcile_cancellations()
        issues.extend(self._flat_sell_issues(owned))
        self.position_agreement = all(
            sum((p["quantity"] for p in owned.values() if p["conid"] == conid), Decimal(0))
            == number(self.positions.get(conid, {}).get("quantity", 0))
            for conid in {p["conid"] for p in owned.values()} | set(self.positions)
        )
        totals = {}
        for position in owned.values():
            totals[position["conid"]] = (
                totals.get(position["conid"], Decimal(0)) + position["quantity"]
            )
            if position["quantity"] < 0:
                issues.append("An owned position has a negative quantity.")
            if position["quantity"] > 0:
                entry = next(o for o in self.store.orders() if o["id"] == position["entry_id"])
                valid = (
                    self.position_agreement
                    and not identity_issues
                    and self._valid_protection(position, entry)
                )
                position["protected"] = valid
                if not valid:
                    issues.append("An owned position lacks verified active protection.")
                    self.incident(
                        "missing_protection",
                        "An owned position lacks verified active protection. "
                        "Cancel the remaining entry and inspect Gateway immediately.",
                    )
                    if not identity_issues:
                        self._repair_protection(position, entry)
        for conid in set(totals) | set(self.positions):
            if totals.get(conid, Decimal(0)) != number(
                self.positions.get(conid, {}).get("quantity", 0)
            ):
                issues.append(
                    "Local and broker positions disagree, or external positions are present."
                )
        if any(o["state"] in {"unknown", "dispatching"} for o in self.store.orders()):
            issues.append("An order outcome remains uncertain.")
        if not {"NetLiquidation", "AvailableFunds", "GrossPositionValue"} <= set(self.facts):
            issues.append("Required USD account facts are missing.")
        self.reconciled = not issues
        self.reconciled_at = time.monotonic()
        self.last_fault = " ".join(dict.fromkeys(issues)) or None
        if self.reconciled:
            self._reconciliation_recovery()
            with self.store.transaction() as db:
                for order in self.store.orders():
                    position = owned.get(order["run_id"])
                    reservation = self.store.read(db, "reservation", order["id"])
                    children = [
                        self.broker_orders.get(order["broker_id"] + offset, {}) for offset in (1, 2)
                    ]
                    active_children = any(
                        child
                        and child.get("status")
                        not in {"Cancelled", "ApiCancelled", "Filled", "Inactive"}
                        for child in children
                    )
                    if (
                        reservation
                        and reservation.get("active")
                        and order["state"] in {"cancelled", "rejected", "filled"}
                        and (not position or position["quantity"] == 0)
                        and not active_children
                    ):
                        reservation["active"] = False
                        self.store.write(db, "reservation", order["id"], reservation)
                        self.store.append(db, "risk.released", {"id": order["id"]})
        for run in self.store.list("run"):
            position = owned.get(run["id"])
            if position and position["quantity"] > 0:
                if run.get("archived"):
                    run.update(
                        archived=False, removal_pending=False, armed=False, late_fill_recovery=True
                    )
                    self.incident(
                        "late_archived_fill",
                        "A removed run received a late execution. Monitor its position and "
                        "protection.",
                    )
                run.update(
                    state="position_open"
                    if position.get("protected") and not run.get("late_fill_recovery")
                    else "recovery_required",
                    position=str(position["quantity"]),
                    protected=position.get("protected", False),
                )
                self.store.put("run", run["id"], run)
            elif run.get("position") != "0":
                run.update(
                    position="0",
                    protected=False,
                    state="armed" if run.get("armed") else "completed",
                )
                self.store.put("run", run["id"], run)
            pending_entry = any(
                o["run_id"] == run["id"]
                and o["payload"].get("purpose", "entry") == "entry"
                and o["state"] not in {"filled", "cancelled", "rejected"}
                for o in self.store.orders()
            )
            if (
                run.get("armed")
                and self.reconciled
                and not pending_entry
                and not (position and position["quantity"] > 0)
            ):
                waiting = run.get("valid_from", "") > now()
                ready = self.data.get(run["conid"], {}).get("warm")
                run.update(
                    state="waiting_session" if waiting else "armed" if ready else "waiting_data",
                    blocking_reason=None,
                )
                self.store.put("run", run["id"], run)
            if not position or position["quantity"] == 0:
                if self.store.get("exit_request", run["id"]):
                    self.store.put("exit_request", run["id"], {})
        self.store.event(
            "reconciliation.finished",
            {
                "ready": self.reconciled,
                "issues": issues,
                "positions": list(self.positions.values()),
                "account_facts": self.facts,
                "broker_orders": list(self.broker_orders.values()),
            },
        )
        if self.reconciled and type(self.broker) is PaperGateway:
            evidence = self.store.get("qualification", "broker_evidence") or {}
            for position in owned.values():
                key = position["run_id"]
                if (self.store.get("run", key) or {}).get("diagnostic_test"):
                    continue
                trial = self.store.get("paper_trial", key) or {}
                if position["quantity"] > 0 and position.get("protected"):
                    trial["protection_observed"] = True
                    self.store.event(
                        "protection.verified",
                        {"run_id": key, "quantity": str(position["quantity"])},
                    )
                    if self.store.get("protection_repair", position["entry_id"]):
                        evidence["partial_repair_verified"] = True
                if position["quantity"] == 0 and trial.get("protection_observed"):
                    evidence["smoke_completed"] = True
                    trial["closed_and_reconciled"] = True
                self.store.put("paper_trial", key, trial)
            if (
                self._recovered_context
                and self.data
                and all(d.get("warm") for d in self.data.values())
            ):
                evidence["temporary_recovery"] = True
                self._recovered_context = False
            self.store.put("qualification", "broker_evidence", evidence)

    def readiness(self):
        critical = [
            i
            for i in self.store.list("incident")
            if not i.get("resolved") and i.get("severity", "critical") == "critical"
        ]
        return [
            check(
                "sdk_compatibility",
                "Gateway API compatibility",
                self.server_version is not None and self.server_version >= 220,
                "Use the pinned offline Gateway build with protocol 220 or later.",
            ),
            check(
                "clock",
                "Clock synchronized",
                self.clock_ok,
                "Synchronize Windows time and receive a Gateway heartbeat.",
            ),
            check(
                "gateway",
                "Gateway handshake",
                self.connected,
                "Connect the paper Gateway on this PC at port 4002.",
            ),
            check(
                "paper_context",
                "Verified paper login",
                self.attested and self.broker.paper_context,
                "Confirm the paper login after Gateway completes its handshake.",
            ),
            check(
                "reconciliation",
                "Orders and positions reconciled",
                self.reconciled and time.monotonic() - self.reconciled_at < 30,
                self.last_fault
                or "Compare account facts, orders, executions, positions and protection.",
            ),
            check(
                "emergency",
                "Emergency stop clear",
                not self.store.emergency(),
                "Review and clear emergency stop before fresh entry authorization.",
                "/desk",
            ),
            check(
                "incidents",
                "Critical incidents resolved",
                not critical,
                "Resolve outstanding incidents and reconcile.",
                "/activity",
            ),
            check(
                "broker_funds",
                "Broker account facts",
                number(self.facts.get("AvailableFunds", 0)) > 0
                and number(self.facts.get("GrossPositionValue", 5001)) <= 5000,
                "Positive available USD funds and gross exposure within $5,000 are required.",
            ),
            check(
                "daily_loss",
                "Daily loss within $100",
                self.daily_pnl is not None
                and self.daily_pnl > -100
                and time.monotonic() - self.pnl_at < 30,
                "Current broker daily P/L, including unrealized P/L, must be above −$100.",
            ),
        ]

    def review_incident(self, identity):
        incident = self.incident_detail(identity)
        if not incident["can_resolve"]:
            raise Conflict(incident["remediation"])
        incident = {k: v for k, v in incident.items() if k not in {"can_resolve", "remediation"}}
        if not incident:
            raise ValueError("Incident not found.")
        if not self.reconciled or not self.connected or not self.attested:
            raise Conflict(
                "Complete paper attestation and reconciliation before reviewing this incident."
            )
        if identity == "callback_overflow" and self.broker.overflow.is_set():
            raise Conflict("Restart the application and reconcile after a callback overflow.")
        if identity == "clock_skew" and not self.clock_ok:
            raise Conflict("Synchronize Windows time and receive a valid heartbeat first.")
        if identity == "history_timeout" and any(not d.get("warm") for d in self.data.values()):
            raise Conflict("Repair historical data before clearing this incident.")
        incident.update(resolved=True, reviewed_at=now())
        with self.store.transaction() as db:
            self.store.write(db, "incident", identity, incident)
            self.store.append(db, "incident.reviewed", {"id": identity})
        return incident

    def snapshot(self):
        checks = self.readiness()
        evaluations = {}
        for key, state in self.runtime.items():
            values = state.get("last_result", {}).get("values", {})
            evaluations[key] = [
                {
                    "node": node["id"],
                    "label": node.get("label", node["kind"]),
                    "value": str(values[node["id"]])
                    if isinstance(values.get(node["id"]), Decimal)
                    else values.get(node["id"]),
                }
                for node in state["graph"].ordered
            ]
        return {
            "mode": "paper",
            "connection": "connected"
            if self.connected
            else "connecting"
            if self.requested_connection
            else "disconnected",
            "attested": self.attested,
            "server_version": self.server_version,
            "entry_permission": all(c["passed"] for c in checks)
            and any(
                r.get("armed")
                and r.get("expires_at", "") > now()
                and self._session_permission(r)
                and self.data.get(r["conid"], {}).get("warm")
                for r in self.store.list("run")
            ),
            "emergency": self.store.emergency(),
            "checks": checks,
            "runs": self.store.list("run"),
            "orders": self.store.orders(),
            "positions": [
                {**p, "quantity": str(p["quantity"]), "cash": str(p["cash"])}
                for p in self.owned().values()
            ],
            "broker_positions": list(self.positions.values()),
            "data": copy.deepcopy(list(self.data.values())),
            "contracts": list(self.contracts.values()),
            "incidents": self.store.list("incident"),
            "account_facts": dict(self.facts),
            "timestamp": now(),
            "evaluations": evaluations,
        }

    def order_detail(self, identity):
        order = next((o for o in self.store.orders() if o["id"] == identity), None)
        if not order:
            raise ValueError("Order not found.")
        run = self.store.get("run", order["run_id"])
        with self.store.connect() as db:
            executions = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM executions WHERE order_id=?", (identity,)
                )
            ]
            timeline = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT json_object('timestamp',timestamp,'type',type,'payload',json(payload)) "
                    "FROM events WHERE json_extract(payload,'run_id')=? "
                    "OR json_extract(payload,'id')=? ORDER BY sequence DESC LIMIT 200",
                    (order["run_id"], identity),
                )
            ]
        return {
            "order": order,
            "run": run,
            "executions": executions,
            "broker_observations": [
                self.store.get("broker_order", str(key)) for key in order_ids(order)
            ],
            "timeline": timeline,
        }

    def create_run(self, strategy_id, version, conid):
        published = self.store.version(strategy_id, version)
        if conid not in self.contracts:
            raise ValueError("Resolve and select a Gateway contract in Settings first.")
        symbol = self.contracts[conid]["symbol"]
        if symbol != published["document"]["settings"]["symbol"]:
            raise ValueError("The resolved symbol must match the published strategy symbol.")
        run = {
            "id": uuid.uuid4().hex,
            "name": published["name"],
            "version": version,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "conid": conid,
            "state": "ready",
            "armed": False,
            "position": "0",
            "protected": False,
            "entries": 0,
            "risk": published["document"]["settings"]["risk"],
            "created_at": now(),
            "blocking_reason": "Review the session before arming.",
        }
        self.store.put("run", run["id"], run)
        self.store.event(
            "run.created", {"run_id": run["id"], "strategy_id": strategy_id, "version": version}
        )
        self.subscribe(conid)
        return run

    def arm_preview(
        self, ids, profile_id="smoke", profile_version=1, unattended=False, session_date=None
    ):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 5 or len(set(ids)) != len(ids):
            raise ValueError("Select one to five distinct runs.")
        checks = self.readiness()
        profile = self.store.get("risk_profile", f"{profile_id}:{profile_version}")
        if not profile:
            raise ValueError("Select a published risk profile.")
        checks.extend(qualification_checks(self.store, profile, unattended, self.code_verified))
        selected = []
        from .sessions import NY, execution_bounds, next_session_day

        stamp = datetime.now(UTC)
        if session_date is None:
            hours = []
            for key in ids:
                item = self.store.get("run", key)
                if not item:
                    raise ValueError("A selected run no longer exists.")
                settings = self.store.version(item["strategy_id"], item["version"])["document"][
                    "settings"
                ]
                hours.append(settings.get("trading_hours", "regular"))
            session_date = next_session_day(
                stamp, "extended" if all(h == "extended" for h in hours) else "regular"
            )
        try:
            selected_day = datetime.fromisoformat(session_date).date()
        except ValueError as exc:
            raise ValueError("Select an exchange date.") from exc
        delta = (selected_day - stamp.astimezone(NY).date()).days
        checks.append(
            check(
                "session_date",
                "Selected exchange date",
                0 <= delta <= 7,
                "Choose an exchange session within the next seven days.",
                "/desk",
            )
        )
        windows = []
        active = [r for r in self.store.list("run") if r.get("armed") and r["id"] not in ids]
        for key in ids:
            run = self.store.get("run", key)
            if not run:
                raise ValueError("A selected run no longer exists.")
            if run.get("archived") or run.get("removal_pending") or run.get("diagnostic_test"):
                raise Conflict("Select an active strategy run.")
            run = dict(run)
            settings = self.store.version(run["strategy_id"], run["version"])["document"][
                "settings"
            ]
            hours = settings.get("trading_hours", "regular")
            bounds = execution_bounds(session_date, hours, self.contracts.get(run["conid"]))
            deferred = bool(bounds and stamp < bounds[0])
            run.update(
                trading_hours=hours,
                session_date=session_date,
                valid_from=bounds[0].isoformat() if bounds else None,
                expires_at=bounds[1].isoformat() if bounds else None,
            )
            if bounds:
                windows.append(bounds)
            checks.append(
                check(
                    "session_" + key,
                    f"{run['symbol']} execution window",
                    bounds and stamp < bounds[1] - timedelta(minutes=15),
                    "Select a supported broker session; extended hours need a current "
                    "contract schedule.",
                    "/settings",
                )
            )
            checks.append(
                check(
                    "extended_qualification_" + key,
                    "Extended-hours supervision",
                    hours != "extended" or not unattended,
                    "Extended hours currently require a supervised paper session.",
                    "/desk",
                )
            )
            selected.append(run)
            data = self.data.get(run["conid"], {})
            fresh = (
                data.get("received_at")
                and (
                    datetime.now(UTC) - datetime.fromisoformat(data["received_at"])
                ).total_seconds()
                <= 15
            )
            checks.append(
                check(
                    "data_" + key,
                    f"{run['symbol']} data and warm-up",
                    deferred or (data.get("live") and data.get("warm") and fresh),
                    "Before opening, data checks are deferred. Fresh data and complete "
                    "warm-up remain mandatory at submission.",
                    "/settings",
                )
            )
            evaluated = self._runtime(run).get("last_result", {}) if data.get("warm") else {}
            checks.append(
                check(
                    "indicators_" + key,
                    f"{run['symbol']} strategy inputs ready",
                    deferred
                    or (evaluated.get("entry") is not None and evaluated.get("stop") is not None),
                    "Wait for required calculations and the protective stop to warm up.",
                    "/studio",
                )
            )
            checks.append(
                check(
                    "run_" + key,
                    f"{run['symbol']} position ownership",
                    not run.get("armed") and number(run.get("position", 0)) == 0,
                    "Disarm or complete the existing run before issuing new authorization.",
                    "/desk",
                )
            )
        symbols = [r["symbol"] for r in active + selected]
        checks.append(
            check(
                "distinct_symbols",
                "Distinct symbols and capacity",
                len(symbols) == len(set(symbols)) and len(symbols) <= 5,
                "Use at most five runs on distinct symbols.",
                "/desk",
            )
        )
        checks.append(
            check(
                "profile_capacity",
                "Selected risk-profile capacity",
                len(active + selected) <= profile["runs"],
                f"This profile allows {profile['runs']} runs and "
                f"up to {profile['shares']} shares per run.",
                "/settings",
            )
        )
        bounds = (min(w[0] for w in windows), max(w[1] for w in windows)) if windows else None
        return {
            "eligible": all(c["passed"] for c in checks),
            "checks": checks,
            "runs": selected,
            "session_date": session_date,
            "valid_from": bounds[0].isoformat() if bounds else None,
            "expires_at": bounds[1].isoformat() if bounds else None,
            "entry_cutoff": (bounds[1] - timedelta(minutes=15)).isoformat() if bounds else None,
            "limits": profile,
            "summaries": [
                {"run_id": run["id"], **self.store.version(run["strategy_id"], run["version"])}
                for run in selected
            ],
            "authorization": "unattended_paper_session"
            if unattended
            else "supervised_paper_session",
        }

    def arm(
        self,
        ids,
        mutation_id,
        profile_id="smoke",
        profile_version=1,
        unattended=False,
        session_date=None,
    ):
        prior = self.store.get("mutation", mutation_id)
        if prior:
            if (
                prior["ids"] != ids
                or prior.get("profile_id", "smoke") != profile_id
                or prior.get("profile_version", 1) != profile_version
                or prior.get("unattended", False) != unattended
                or prior.get("requested_session_date") != session_date
            ):
                raise Conflict("This action identifier was already used for a different selection.")
            return prior["result"]
        preview = self.arm_preview(ids, profile_id, profile_version, unattended, session_date)
        if not preview["eligible"]:
            raise Conflict(
                "The selected runs are blocked. Resolve the readiness checks and review again."
            )
        with self.store.transaction() as db:
            for run in preview["runs"]:
                if (self.store.read(db, "safety", "emergency") or {}).get("active"):
                    raise Conflict("Emergency stop became active. Review the session again.")
                run.update(
                    armed=True,
                    state="waiting_session" if run["valid_from"] > now() else "armed",
                    expires_at=run["expires_at"],
                    authorized_at=now(),
                    authorization_id=mutation_id,
                    epoch=self.broker.epoch,
                    blocking_reason=None,
                    limits=preview["limits"],
                    unattended=unattended,
                    entries=run.get("entries", 0)
                    if self.store.get("run", run["id"]).get("session_date")
                    == preview["session_date"]
                    else 0,
                    session_date=preview["session_date"],
                )
                self.store.write(db, "run", run["id"], run)
                self.store.append(
                    db,
                    "run.authorized",
                    {
                        "run_id": run["id"],
                        "version": run["version"],
                        "expires_at": run["expires_at"],
                        "scope": preview["authorization"],
                        "limits": preview["limits"],
                    },
                )
            self.store.write(
                db,
                "mutation",
                mutation_id,
                {
                    "ids": ids,
                    "profile_id": profile_id,
                    "profile_version": profile_version,
                    "unattended": unattended,
                    "requested_session_date": session_date,
                    "result": {"armed": ids},
                },
            )
        for run in preview["runs"]:
            self._runtime(run)
        return {"armed": ids}

    def disarm(self, key, reason="Disarmed by operator."):
        run = self.store.get("run", key)
        if not run:
            raise ValueError("Run not found.")
        run.update(
            armed=False,
            state="position_open" if number(run["position"]) else "paused",
            blocking_reason=reason,
        )
        self.store.put("run", key, run)
        self.store.event("run.disarmed", {"run_id": key, "reason": reason})
        for order in self.store.orders():
            if (
                order["run_id"] == key
                and order["payload"].get("purpose", "entry") == "entry"
                and order["state"] in {"working", "dispatching"}
            ):
                self.cancel_entry(order["id"])
        return run

    def emergency(self, active):
        self.store.set_emergency(active)
        if active:
            for run in self.store.list("run"):
                self.disarm(run["id"], "Emergency stop is active.")
        return {"active": active}

    def cancel_entry(self, key):
        order = next((o for o in self.store.orders() if o["id"] == key), None)
        if not order or order["payload"].get("purpose", "entry") != "entry":
            raise ValueError("Select a known entry order.")
        if order["state"] in {"cancel_pending", "cancelled", "filled", "rejected"}:
            return {"state": order["state"]}
        self.store.transition(key, "cancel_pending", {"action": "cancel_requested"})
        self._queue_cancel(order["broker_id"], "entry")
        return {"state": "cancel_pending"}

    def _runtime(self, run, reset=False):
        if run["id"] not in self.runtime or reset:
            graph = compile_graph(
                self.store.version(run["strategy_id"], run["version"])["document"]
            )
            market = Market(graph)
            bars = self.history_bars.get(run["conid"], {60: {}, 5: {}})
            stamp = datetime.now(UTC).replace(second=0, microsecond=0)
            completed = [int(key) + 60 for key in bars[60] if int(key) + 60 <= stamp.timestamp()]
            if completed:
                stamp = datetime.fromtimestamp(max(completed), UTC)
            market.seed(list(bars[60].values()), list(bars[5].values()), stamp)
            if run.get("last_fill_at"):
                market.last_entry = datetime.fromisoformat(run["last_fill_at"])
            self.runtime[run["id"]] = {
                "graph": graph,
                "market": market,
                "previous": {},
                "entry": False,
                "seeded": False,
                "last_bar": None,
            }
            state = self.runtime[run["id"]]
            start = market.bar_seed_until or stamp
            for observation in self.buffered_ticks.get(run["conid"], []):
                timestamp = datetime.fromtimestamp(observation["timestamp"], UTC)
                if timestamp < start:
                    continue
                completed = market.close_clock(timestamp)
                if completed is not None:
                    evaluate_step(state, completed)
                context = market.accept(
                    timestamp, number(observation["price"]), number(observation["size"])
                )
                state["primed_sequence"] = observation.get("sequence")
                if context is None or (
                    graph.document["settings"]["evaluation"] == "bar_close"
                    and not context["bar_closed"]
                ):
                    continue
                evaluate_step(state, context)
        return self.runtime[run["id"]]

    def _tick(self, event):
        conid = event["conid"]
        if conid not in self.data:
            return
        stamp = datetime.fromtimestamp(event["timestamp"], UTC)
        previous_received = self.data[conid].get("received_at")
        if (
            self.data[conid].get("warm")
            and previous_received
            and (datetime.now(UTC) - datetime.fromisoformat(previous_received)).total_seconds() > 15
        ):
            self._data_gap(conid, "A trade arrived after a stale-data gap.")
        self.data[conid].update(
            price=event["price"], received_at=now(), source_at=stamp.isoformat()
        )
        capture = event.get("capture") or self.store.capture({"source": "ibkr_last", **event})
        buffer = self.buffered_ticks.setdefault(conid, deque(maxlen=200000))
        if not self.data[conid].get("warm") and len(buffer) == buffer.maxlen:
            self.incident(
                "warmup_overflow",
                "The warm-up tick buffer filled. Reduce subscriptions and repair history.",
            )
            return
        buffer.append(event)
        if abs((datetime.now(UTC) - stamp).total_seconds()) > 15:
            if self.data[conid].get("warm"):
                self._data_gap(conid, "Trade timestamps are stale or ahead of the clock.")
            return
        if not self.data[conid].get("warm"):
            return
        for run in getattr(self, "_batch_runs", None) or self.store.list("run"):
            if run["conid"] != conid or run.get("archived") or run.get("diagnostic_test"):
                continue
            state = self._runtime(run)
            if (
                event.get("sequence") is not None
                and state.get("primed_sequence") == event["sequence"]
            ):
                continue
            market, graph = state["market"], state["graph"]
            closed_context = market.close_clock(stamp)
            if closed_context is not None:
                self._evaluate_context(run, state, closed_context, capture)
            try:
                context = market.accept(stamp, number(event["price"]), number(event["size"]))
            except GraphError:
                self._data_gap(conid, "Late or invalid observations require candle repair.")
                return
            if context is None:
                continue
            eligible = (
                graph.document["settings"]["evaluation"] == "intrabar" or context["bar_closed"]
            )
            if not eligible:
                continue
            self._evaluate_context(run, state, context, capture)

    def _evaluate_context(self, run, state, context, capture):
        graph = state["graph"]
        seeded = state["seeded"]
        result, signal = evaluate_step(state, context)
        if not seeded:
            return  # Warm-up never creates retrospective entries.
        position = self.owned().get(run["id"])
        if position and position["quantity"] > 0:
            if (
                result["exit"] is True
                or context["minutes_to_close"] <= graph.document["settings"]["exit_before_close"]
            ):
                self._request_exit(run["id"])
        elif run.get("armed") and signal and self._session_permission(run):
            state["last_bar"] = context["bar_start"]
            run["last_signal"] = now()
            self.store.put("run", run["id"], run)
            self.store.event(
                "strategy.signal",
                {"run_id": run["id"], "capture": capture, "strategy_hash": graph.digest},
            )
            try:
                self._enter(run, result, context, capture)
            except (ValueError, Conflict) as exc:
                run["blocking_reason"] = str(exc)
                self.store.put("run", run["id"], run)
                self.store.event("risk.blocked", {"run_id": run["id"], "reason": str(exc)})

    def _request_exit(self, key):
        if not self.store.get("exit_request", key):
            self.store.put("exit_request", key, {"requested_at": now()})
            self.store.event("exit.requested", {"run_id": key})
        try:
            self.close_position(key)
        except Conflict:
            pass  # The durable request remains pending; broker protection is retained.

    def _clock_evaluations(self):
        stamp = datetime.now(UTC)
        for run in self.store.list("run"):
            if not run.get("armed") and self.owned().get(run["id"], {}).get("quantity", 0) <= 0:
                continue
            if run.get("diagnostic_test"):
                bounds = self._run_bounds(run, stamp)
                position = self.owned().get(run["id"], {}).get("quantity", 0)
                if position > 0 and (
                    self.store.get("exit_request", run["id"])
                    or bounds
                    and stamp >= bounds[1] - timedelta(minutes=5)
                ):
                    self._request_exit(run["id"])
                continue
            data = self.data.get(run["conid"], {})
            state = self._runtime(run)
            context = (
                state["market"].close_clock(stamp - timedelta(seconds=2))
                if data.get("warm") and data.get("live")
                else None
            )
            if context is not None:
                capture = self.store.capture(
                    {
                        "source": "candle_close_clock",
                        "timestamp": stamp.isoformat(),
                        "conid": run["conid"],
                    }
                )
                self._evaluate_context(run, state, context, capture)
            bounds = self._run_bounds(run, stamp)
            if (
                bounds
                and bounds[0] <= stamp
                and stamp
                >= bounds[1]
                - timedelta(minutes=state["graph"].document["settings"]["exit_before_close"])
            ):
                position = self.owned().get(run["id"])
                if position and position["quantity"] > 0:
                    self._request_exit(run["id"])
            elif self.store.get("exit_request", run["id"]):
                position = self.owned().get(run["id"])
                if position and position["quantity"] > 0:
                    self._request_exit(run["id"])

    def _enter(self, run, result, context, capture):
        if (
            not all(c["passed"] for c in self.readiness())
            or (not run.get("diagnostic_test") and not self.data[run["conid"]].get("warm"))
            or not self.data[run["conid"]].get("live")
        ):
            raise Conflict("Connection, reconciliation, data or incident readiness blocks entries.")
        if context["minutes_to_close"] <= 15 or run["expires_at"] <= now():
            raise Conflict("The entry session has ended.")
        if run.get("valid_from"):
            bounds = self._run_bounds(run)
            if not self._session_permission(run) or datetime.now(UTC) >= bounds[1] - timedelta(
                minutes=15
            ):
                raise Conflict("The selected execution session is not open for new entries.")
        graph = self._runtime(run)["graph"]
        settings = graph.document["settings"]
        profile = run.get(
            "limits",
            {
                "shares": 1,
                "planned_stop_risk": "10",
                "notional": "1000",
                "daily_loss": "100",
                "entry_timeout": 30,
            },
        )
        if run["entries"] >= settings["max_entries"]:
            raise Conflict("The session entry limit has been reached.")
        quotes = self.quotes.get(run["conid"], {})
        if any(
            side not in quotes
            or (
                datetime.now(UTC) - datetime.fromisoformat(quotes[side]["received_at"])
            ).total_seconds()
            > 15
            for side in ("bid", "ask")
        ):
            raise Conflict("Current bid and ask quotes are required.")
        limit = number(quotes["ask"]["price"])
        if run.get("diagnostic_test"):
            limit = number(result["test_limit"])
            if limit >= number(quotes["bid"]["price"]):
                raise Conflict(
                    "The reviewed test price is no longer below bid. Refresh the preview."
                )
        contract = self.contracts[run["conid"]]
        increments = self.market_rules.get(contract.get("market_rule"), [])
        if not increments:
            raise Conflict("Broker price-increment rules have not been received.")

        def increment(price):
            return number(
                next((p["increment"] for p in reversed(increments) if price >= number(p["low"])), 0)
            )

        tick = increment(limit)
        if tick <= 0:
            raise Conflict("A valid contract price increment is required.")
        stop = result["stop"]
        if stop is None:
            raise Conflict("The protective stop has not warmed up.")
        tick = increment(stop)
        if tick <= 0:
            raise Conflict("The stop price has no qualified broker increment.")
        stop = (stop / tick).to_integral_value(rounding=ROUND_DOWN) * tick
        if not Decimal(0) < stop < limit:
            raise Conflict("The protective stop must be positive and below the entry limit.")
        extended = settings.get("trading_hours") == "extended"
        protective_limit = stop
        if extended:
            protective_limit = stop - number(settings["stop_limit_offset"])
            tick = increment(protective_limit)
            if tick <= 0 or protective_limit <= 0:
                raise Conflict(
                    "The protective stop-limit price must be positive with a valid increment."
                )
            protective_limit = (protective_limit / tick).to_integral_value(
                rounding=ROUND_DOWN
            ) * tick
            if not 0 < protective_limit < stop:
                raise Conflict("The protective limit must be below the stop trigger.")
        reserved_funds = sum(
            (number(r["notional"]) for r in self.store.list("reservation") if r.get("active")),
            Decimal(0),
        )
        quantity = size_entry(
            settings,
            profile,
            limit,
            protective_limit,
            number(self.facts["AvailableFunds"]) - reserved_funds,
        )
        target = result["target"]
        if target is None and any(node["kind"] == "target" for node in graph.ordered):
            raise Conflict("The configured profit target has not warmed up.")
        if target is not None:
            tick = increment(target)
            if tick <= 0:
                raise Conflict("The target price has no qualified broker increment.")
            target = (target / tick).to_integral_value(rounding=ROUND_DOWN) * tick
            if target <= limit:
                raise Conflict("The profit target must exceed the entry limit.")
        # Include marked-to-market owned P/L and reported commissions. Missing
        # quotes conservatively block the calculation rather than becoming zero.
        pnl = self.daily_pnl
        if pnl is None or time.monotonic() - self.pnl_at >= 30:
            raise Conflict("Current broker daily P/L is unavailable.")
        for position in self.owned().values():
            data = self.data.get(position["conid"], {})
            if position["quantity"] and not data.get("price"):
                raise Conflict("Current position marks are unavailable.")
        pnl -= sum(
            (
                number(c["amount"])
                for c in self.store.list("commission")
                if c["currency"] == "USD" and c.get("received_at", "")[:10] == now()[:10]
            ),
            Decimal(0),
        )
        if pnl <= -number(profile["daily_loss"]):
            raise Conflict("The daily loss stop blocks new entries.")
        key = uuid.uuid4().hex
        payload = {
            "purpose": "entry",
            "outside_rth": extended,
            "stop_limit": str(protective_limit) if extended else None,
            "conid": run["conid"],
            "symbol": run["symbol"],
            "quantity": quantity,
            "limit": str(limit),
            "stop": str(stop),
            "target": str(target) if target else None,
            "timeout": min(settings["entry_timeout"], profile["entry_timeout"]),
            "expires_at": (
                datetime.now(UTC)
                + timedelta(seconds=min(settings["entry_timeout"], profile["entry_timeout"]))
            ).isoformat(),
            "capture": capture,
            "quote_capture": self.store.capture(
                {"source": "entry_quotes", "conid": run["conid"], "quotes": quotes}
            ),
        }
        reserved = self.store.reserve_order(
            key,
            payload,
            run["id"],
            self.next_id,
            {
                "symbol": run["symbol"],
                "risk": str(quantity * (limit - protective_limit)),
                "notional": str(quantity * limit),
            },
        )
        self.store.mark_dispatch(key)
        try:
            self.broker.submit_bracket({**payload, **reserved})
        except Exception:
            self.store.transition(key, "unknown", {"reason": "dispatch_interrupted"})
            self.incident(
                "dispatch_uncertain",
                "Order dispatch was interrupted. Do not resend; reconcile in Gateway.",
            )
        run.update(
            entries=run["entries"] + 1,
            state="entry_working",
            blocking_reason=None,
            last_signal=now(),
        )
        self.store.put("run", run["id"], run)
        self.reconciled = False
        self.next_reconcile = time.monotonic() + 2

    def close_position(self, key):
        position = self.owned().get(key)
        if (
            not position
            or position["quantity"] <= 0
            or position["quantity"] != position["quantity"].to_integral_value()
        ):
            raise Conflict("A reconciled owned whole-share position is required.")
        if not self.reconciled or not self.attested or time.monotonic() - self.reconciled_at >= 30:
            raise Conflict("Reconcile the paper account before closing an owned position.")
        self.store.put("exit_request", key, {"requested_at": now()})
        run = self.store.get("run", key) or {}
        if run.get("valid_from"):
            from .sessions import NY, execution_bounds

            stamp = datetime.now(UTC)
            bounds = execution_bounds(
                stamp.astimezone(NY).date().isoformat(),
                run.get("trading_hours", "regular"),
                self.contracts.get(position["conid"]),
            )
            if not bounds or not bounds[0] <= stamp < bounds[1]:
                raise Conflict(
                    "The selected broker session is closed. "
                    "Exit remains pending; protection is retained."
                )
        if any(
            o["run_id"] == key
            and o["payload"].get("purpose") == "exit"
            and o["state"] not in {"cancelled", "rejected", "filled"}
            for o in self.store.orders()
        ):
            return {"state": "exit_pending"}
        quote = self.quotes.get(position["conid"], {}).get("bid")
        if (
            not quote
            or (datetime.now(UTC) - datetime.fromisoformat(quote["received_at"])).total_seconds()
            > 15
        ):
            raise Conflict("A current bid is required; protective orders remain in place.")
        identity = uuid.uuid4().hex
        payload = {
            "purpose": "exit",
            "outside_rth": run.get("trading_hours") == "extended",
            "entry_id": position["entry_id"],
            "conid": position["conid"],
            "symbol": position["symbol"],
            "quantity": int(position["quantity"]),
            "limit": quote["price"],
            "quote_capture": self.store.capture(
                {"source": "exit_quote", "conid": position["conid"], "quote": quote}
            ),
        }
        reserved = self.store.reserve_order(identity, payload, key, self.next_id)
        self.store.event(
            "exit.risk_checked",
            {
                "run_id": key,
                "quantity": payload["quantity"],
                "reconciled_owned_quantity": str(position["quantity"]),
                "oca_overfill_block": True,
            },
        )
        self.store.mark_dispatch(identity)
        try:
            self.broker.submit_exit({**payload, **reserved})
        except Exception:
            self.store.transition(identity, "unknown", {"reason": "dispatch_interrupted"})
            self.incident(
                "exit_uncertain",
                "An exit request has an uncertain outcome. Reconcile; do not replace it.",
            )
        self.reconciled = False
        self.next_reconcile = time.monotonic() + 2
        run = self.store.get("run", key)
        if run:
            run.update(
                state="exiting", blocking_reason="Exit requested; awaiting broker confirmation."
            )
            self.store.put("run", key, run)
        return {"state": "exit_pending"}
