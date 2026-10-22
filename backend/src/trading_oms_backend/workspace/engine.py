from __future__ import annotations

import copy
import json
import math
import os
import queue
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from .acceptance import observe_session
from .authorization import RESUME_POLICY, Authorization
from .broker import GatewayData, PaperGateway
from .contract_search import ContractSearch
from .contracts import capabilities, execution_kind, execution_reason, reviewed_sizing
from .credit import CreditController
from .crypto_engine import CryptoPaperController
from .data_scheduling import DataScheduling, request_progress
from .data_views import DataViews
from .environment import environment as select_environment
from .feed_recovery import FeedRecovery
from .fx_engine import FXController
from .graph import GraphError, digest, number
from .health import atomic_health, watchdog_status
from .incident_recovery import IncidentRecovery
from .incidents import IncidentBook, safe_fault
from .market import Market, calendar, session_bounds
from .oca import is_pair
from .oca_engine import OCAController
from .oms import OrderLedger
from .operations import OperatorActions
from .outages import OutageNotifications
from .paper_test import PaperConnectionTest
from .power import SleepGuard
from .premarket import PremarketController, premarket
from .preparation import Preparation
from .protection import ProtectionController, order_ids
from .qualification import profiles, qualification_checks
from .reconciliation import Reconciliation
from .reusable import bind_graph
from .run_archive import RunArchive
from .run_policies import RunPolicies
from .runtime import evaluate_step, size_entry
from .stock_engine import StockController
from .stock_market import StockMarket
from .stock_sessions import StockSession
from .store import Conflict, Store, now
from .verification import verified


def check(code, title, passed, detail, remedy="/settings"):
    return {
        "code": code,
        "title": title,
        "passed": bool(passed),
        "detail": detail,
        "remediation": remedy,
        "status": "ready" if passed else "blocked",
        "category": "requirement",
        "scope": {"type": "workspace", "key": "*"},
        "blocking_stages": [] if passed else ["authorization", "dispatch"],
    }


class Engine(
    PaperConnectionTest,
    OperatorActions,
    RunPolicies,
    CreditController,
    DataScheduling,
    FXController,
    Authorization,
    Preparation,
    Reconciliation,
    PremarketController,
    ContractSearch,
    RunArchive,
    StockController,
    FeedRecovery,
    IncidentRecovery,
    OutageNotifications,
    DataViews,
    CryptoPaperController,
    OCAController,
    ProtectionController,
    OrderLedger,
):
    """Single execution owner. HTTP and SDK threads never reduce trading state."""

    def __init__(self, store: Store, broker_factory=None, environment="paper", migration=None):
        self.store = store
        self.incidents = IncidentBook(store)
        self._incident_stability = {}
        self.reconciliation_evidence = None
        self._reconciliation_started = None
        self.migration = migration
        self._execution_factory = broker_factory or PaperGateway
        self.environment = select_environment(environment)
        with store.transaction() as db:
            prior_environment = store.read(db, "workspace", "environment")
            if prior_environment and prior_environment["name"] != environment:
                raise Conflict("This state directory belongs to another execution environment.")
            if (
                not prior_environment
                and self.environment.crypto
                and db.execute("SELECT 1 FROM events LIMIT 1").fetchone()
            ):
                raise Conflict("Crypto simulation requires its own empty state directory.")
            store.write(db, "workspace", "environment", {"name": environment})
        self.process_identity = uuid.uuid4().hex
        self.watchdog_started = time.monotonic()
        self.watchdog_seen = False
        self.health_sequence = 0
        store.put(
            "workspace",
            "engine_owner",
            {
                "instance": self.process_identity,
                "pid": os.getpid(),
                "state": "starting",
            },
        )
        self._next_acceptance_record = 0.0
        self.observations = queue.Queue(maxsize=8192)
        self.commands = queue.Queue(maxsize=64)
        if self.migration_pending:
            self.broker = GatewayData(self.observations)
        elif broker_factory is not None:
            self.broker = broker_factory(self.observations)
        elif self.environment.crypto:
            from .simulator import CryptoSimulator

            self.broker = CryptoSimulator(self.observations, store)
        else:
            self.broker = PaperGateway(self.observations)
        self.stopping = threading.Event()
        self.thread = None
        self.connected = self.attested = self.reconciled = False
        self.requested_connection = False
        self.heartbeat_at = self.reconciled_at = 0.0
        self.next_heartbeat = self.next_reconcile = self.next_connect = 0.0
        self.reconnect_delay = 1
        self.connecting_until = 0.0
        self.next_id = 0
        self.reconcile_parts = set()
        self.reconcile_inflight = False
        self.reconcile_deadline = 0.0
        self.positions, self.broker_orders, self.facts = {}, {}, {}
        self.currency_facts = {}
        self.contracts, self.quotes, self.data, self.runtime = {}, {}, {}, {}
        self.history_jobs, self.history_pending, self.history_bars = [], {}, {}
        self.init_feed_recovery()
        self.buffered_ticks, self.repair_requests = {}, {}
        self.history_request_times = deque()
        self.next_history = 0.0
        self.last_fault = None
        self.server_version = None
        self.last_loop = time.monotonic()
        self._next_health_write = 0.0
        self.pnl_currency = None
        self.daily_pnl = None
        self.pnl_at = 0.0
        self.pnl_received_at = None
        self.pnl_diagnostic = None
        self._resume_attestation = False
        self.clock_ok = False
        self.market_rules = {}
        self.fx_quotes = {}
        self.pending_subscriptions = set()
        self.shortable = {}
        self.display_bars = {}
        self._next_runtime_clock = 0.0
        self.position_agreement = False
        self.code_verified = verified()
        self._recovered_context = False
        self.sleep_guard = SleepGuard()
        if not self.migration_pending:
            profiles(store, simulation=self.environment.crypto)
            self._restore()
        self.incidents.current_evaluator = self.current_condition

    @property
    def migration_pending(self):
        return self.migration is not None and self.migration.pending

    def activate_after_migration(self):
        if self.migration_pending:
            raise Conflict("Workspace migration must complete before execution activation.")
        self.broker.disconnect()
        self.broker = self._execution_factory(self.observations)
        profiles(self.store)
        self._restore()
        self.connect()

    def _dispatch(self, method, kwargs):
        if self.migration_pending:
            return self.migration.dispatch(self, method, kwargs)
        if method not in {"overview", "snapshot", "candles", "order_detail"}:
            self._overview_cache = None
        return getattr(self, method)(**kwargs)

    def _restore(self):
        self.store.verify()
        with self.store.transaction() as db:
            self.incidents.reclassify_informational_in(db, "broker_2119")
            incident = self.store.read(db, "incident", "broker_2119")
            if incident and not incident.get("resolved"):
                incident.update(
                    resolved=True,
                    resolution="Informational farm connection message",
                    reviewed_at=now(),
                )
                self.store.write(db, "incident", "broker_2119", incident)
                self.store.append(
                    db,
                    "incident.reclassified",
                    {"id": "broker_2119", "classification": "informational"},
                )
            rows = db.execute("SELECT id,payload FROM documents WHERE kind='run'").fetchall()
            for row in rows:
                run = json.loads(row["payload"])
                run.update(
                    armed=False,
                    authorization_status="revoked",
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
        ) or any(p["quantity"] != 0 for p in self.owned().values()):
            self.requested_connection = True

    def watchdog_status(self):
        return watchdog_status(self.store, self.process_identity)

    def write_health(self):
        self.health_sequence += 1
        atomic_health(
            self.store.directory / "engine-health.json",
            {
                "version": 1,
                "instance": self.process_identity,
                "pid": os.getpid(),
                "timestamp": time.time(),
                "monotonic": time.monotonic(),
                "sequence": self.health_sequence,
                "migration_pending": self.migration_pending,
                "armed": not self.migration_pending
                and any(r.get("armed") for r in self.store.list("run")),
            },
        )

    def monitor_watchdog(self):
        status = self.watchdog_status()
        if status["ready"]:
            self.watchdog_seen = True
        elif self.watchdog_seen or time.monotonic() - self.watchdog_started >= 30:
            self.incident("watchdog", status["detail"])
            for run in self.store.list("run"):
                if run.get("armed"):
                    self.disarm(run["id"], status["detail"])

    def guard_entry_dispatch(self, key):
        """Last local gate before dispatch; only reserved, never-sent intents can be retired."""
        status = self.watchdog_status()
        order = next((o for o in self.store.orders() if o["id"] == key), None)
        run = self.store.get("run", order["run_id"]) if order else None
        holds = self.incidents.applicable([run or {}])
        watchdog_ready = status["ready"]
        checks = self.readiness([run or {}])
        execution_fresh = bool(
            run
            and (
                self.connection_diagnostics(run["conid"])["eligible"]
                if run.get("diagnostic_test")
                else self._run_feed_health(run)["execution_fresh"]
            )
        )
        permitted = bool(
            run
            and not run.get("archived")
            and run.get("armed")
            and run.get("expires_at", "") > now()
            and self._session_permission(run)
        )
        if self._stock_run(run):
            permitted = (
                permitted
                and self._binding_valid(run)
                and self._stock_session(run).tradable(datetime.now(UTC))
            )
            try:
                from .stock_policy import fx_rate

                fx_rate(run["binding"]["contract"]["currency"], self.fx_quotes.values())
            except Conflict:
                permitted = False
        if self._fx_run(run):
            permitted = (
                permitted
                and self._fx_guard(run)
                and bool(order and self._fx_signal_current(order["payload"].get("signal") or {}))
                and (
                    not self._fx_uses_broker_candles(run)
                    or self._fx_broker_trigger_current(run, order["payload"].get("signal") or {})
                )
            )
        if run and order:
            permitted = permitted and self._credit_dispatch_ready(run, order)
        if (
            status["ready"]
            and not holds
            and all(c["passed"] for c in checks)
            and execution_fresh
            and permitted
        ):
            return True
        if holds:
            status = {
                "ready": False,
                "detail": "An applicable incident restriction blocks entry dispatch.",
            }
        elif watchdog_ready:
            status = {
                "ready": False,
                "detail": "Market data, authorization or readiness changed before dispatch.",
            }
        with self.store.transaction() as db:
            order = db.execute("SELECT * FROM outbox WHERE id=?", (key,)).fetchone()
            if not order or order["state"] != "reserved":
                raise Conflict("Entry outcome requires reconciliation before dispatch.")
            db.execute("UPDATE outbox SET state='cancelled' WHERE id=?", (key,))
            self.store.append(
                db,
                "order.dispatch.blocked",
                {
                    "id": key,
                    "reason": status["detail"],
                    "never_submitted": True,
                },
            )
            reservation = self.store.read(db, "reservation", key)
            if reservation:
                self.store.write(db, "reservation", key, {**reservation, "active": False})
                self.store.append(db, "risk.released", {"id": key, "reason": "never_submitted"})
            group = self.store.read(db, "oca_group", key)
            if group:
                self.store.write(db, "oca_group", key, {**group, "state": "cancelled"})
        if not watchdog_ready:
            self.incident("watchdog", status["detail"])
        # A quiet market alone retires this intent, preserving an otherwise valid authorization.
        if holds or not watchdog_ready or not all(c["passed"] for c in checks) or not permitted:
            self.disarm(order["run_id"], status["detail"])
        return False

    def start(self):
        self.watchdog_started = time.monotonic()
        self.last_loop = self.watchdog_started
        self.store.put(
            "workspace",
            "engine_owner",
            {
                "instance": self.process_identity,
                "pid": os.getpid(),
                "state": "running",
            },
        )
        self.thread = threading.Thread(target=self._loop, name="trading-engine", daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            try:
                self.call("shutdown")
            except (ValueError, TimeoutError):
                self.store.set_emergency(True)
        self.stopping.set()
        with self.store.transaction() as db:
            owner = self.store.read(db, "workspace", "engine_owner") or {}
            if owner.get("instance") == self.process_identity:
                self.store.write(db, "workspace", "engine_owner", {**owner, "state": "stopped"})
        if self.thread:
            self.thread.join(timeout=8)
        if self.migration:
            self.migration.close()
        self.broker.disconnect()

    def shutdown(self):
        for run in self.store.list("run"):
            self.disarm(run["id"], "Application is shutting down; fresh arming is required.")
        self.store.event(
            "application.stopping", {"entries_disarmed": True, "broker_protection_retained": True}
        )

    def call(self, method, **kwargs):
        if not self.thread:
            return self._dispatch(method, kwargs)
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
            operation, observation_kind = "observations", None
            try:
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
                    observation_kind = observation["type"]
                    if observation["type"] in {"tick", "quote"}:
                        observation["capture"] = capture
                    self.observe(observation)
                    self._operation_succeeded(operation, observation_kind)
                self._batch_runs = None
                try:
                    future, method, kwargs = self.commands.get(timeout=0.025)
                except queue.Empty:
                    future = None
                if future is not None and future.set_running_or_notify_cancel():
                    operation, observation_kind = "command:" + method, None
                    try:
                        future.set_result(self._dispatch(method, kwargs))
                        self._operation_succeeded(operation)
                    except (ValueError, KeyError) as exc:
                        future.set_exception(exc)
                    except Exception:
                        future.set_exception(
                            Conflict(
                                "The operation failed. Inspect Activity and recovery readiness."
                            )
                        )
                        raise
                operation, observation_kind = "maintenance", None
                self.maintain()
                self._operation_succeeded(operation)
                self.last_loop = time.monotonic()
            except Exception as exc:
                self._batch_runs = None
                self.invalidate_reconciliation()
                self.last_fault = (
                    "An engine operation failed. New entries are blocked; inspect recovery."
                )
                try:
                    self.incident(
                        "engine_fault",
                        self.last_fault,
                        diagnostic=safe_fault(exc, operation, observation_kind),
                    )
                except Exception:
                    self.stopping.set()
        self.sleep_guard.set(False)

    def incident(self, code, detail, **context):
        if code == "engine_fault":
            self._fault_at = time.monotonic()
            self._fault_retest_pending = True
        self._overview_cache = None
        context.setdefault("connection_epoch", self.broker.epoch)
        from .fault_policy import CORRECTED

        fingerprint = (context.get("diagnostic") or {}).get("fingerprint")
        marker = (self.broker.epoch, fingerprint, self.last_loop)
        if code == "engine_fault" and fingerprint in CORRECTED:
            prior = getattr(self, "_repeated_data_fault", None)
            if prior and prior[0] == marker:
                episode = self.incidents.get(prior[1])
                if (
                    episode
                    and episode["condition"] == "active"
                    and episode["restriction"] != "released"
                ):
                    self.record_duplicate_incident(episode)
                    return episode
            context["new_failure"] = True  # Successful loop progress separates recurrences.
        result = self.incidents.raise_incident(code, detail, self.process_identity, **context)
        self._repeated_data_fault = (marker, result["id"]) if code == "engine_fault" else None
        return result

    def connect(self):
        self.operator_disconnected = False
        self.requested_connection = True
        self.next_connect = time.monotonic()
        self.store.event("connection.requested", {"endpoint": "localhost paper Gateway"})
        return {"state": "connecting"}

    def disconnect(self):
        self.operator_disconnected = True
        for run in self.store.list("run"):
            self.disarm(run["id"], "Operator disconnected; existing local protection is suspended.")
        self.requested_connection = False
        self.broker.disconnect()
        self._connection_lost("Operator disconnected; no automatic liquidation.")
        return {"state": "disconnected"}

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
        wanted = {
            s["conid"]: s.get("contract", {})
            for s in self.store.list("subscription")
            if s.get("active")
        }
        for run in self._data_dependencies()["runs"]:
            wanted[run["conid"]] = (run.get("binding") or {}).get(
                "contract", self.contracts.get(run["conid"], {})
            )
        for conid, contract in wanted.items():
            self.broker.resolve(
                conid=conid, exchange=contract.get("routing_exchange", contract.get("exchange", ""))
            )
        self.pending_subscriptions.update(self.data)

    def _invalidate_authorizations(self, reason):
        # A changed account context must not send cancellations into the new account.
        with self.store.transaction() as db:
            for run in self.store.list("run"):
                run.update(
                    armed=False,
                    authorization_status="revoked",
                    state="recovery_required",
                    blocking_reason=reason,
                )
                self.store.write(db, "run", run["id"], run)
            self.store.append(db, "authorization.invalidated", {"reason": reason})

    def _data_gap(
        self, conid, reason, regular_history_only=False, routine_recovery=False, history_only=False
    ):
        if not regular_history_only and conid in getattr(self, "premarket_history", {}):
            self._premarket_queue(conid, force=True)
        data = self.data[conid]
        data.update(
            warm=False,
            repair_after=(
                datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1, seconds=2)
            ).isoformat(),
        )
        if not regular_history_only:
            self.buffered_ticks[conid] = deque(maxlen=200000)
        self.store.event("market.gap", {"conid": conid, "reason": reason})
        for run in self.store.list("run"):
            if run["conid"] == conid and (
                run.get("armed") or run.get("authorization_status") == "temporarily_suspended"
            ):
                if regular_history_only and premarket(run):
                    continue
                if history_only and not self._requires_downloaded_history(run):
                    continue
                if routine_recovery and run.get("authorization_status") == "temporarily_suspended":
                    continue
                self.disarm(
                    run["id"],
                    "Market-data interruption; repair and manually re-arm for new entries.",
                )

    def begin_reconcile(self):
        if not self.connected or not self.broker.paper_context:
            raise Conflict("Connect exactly one paper account before reconciliation.")
        if self.reconcile_inflight:
            return {"state": "reconciling"}
        self.reconcile_inflight = True
        self._reconciliation_started = {
            "id": uuid.uuid4().hex,
            "instance": self.process_identity,
            "epoch": self.broker.epoch,
            "started_at": now(),
            "started_sequence": self.incidents.watermark(),
        }
        self.reconcile_deadline = time.monotonic() + 30
        self.reconcile_parts = set()
        self._reconciliation_retries = 0
        self._stage_reconciliation()
        self.broker.reconcile()
        self.next_reconcile = time.monotonic() + 15
        self.store.event("reconciliation.started", dict(self._reconciliation_started))
        return {"state": "reconciling"}

    def subscribe(self, conid):
        if conid not in self.contracts or self.contracts[conid].get("resolved") is False:
            raise ValueError("Select a fully resolved contract first.")
        queued = self.broker.subscribe(conid) is False
        if queued:
            self.pending_subscriptions.add(conid)
        if conid not in self.data:
            self.data[conid] = {
                "conid": conid,
                "symbol": self.contracts[conid]["symbol"],
                "subscription_status": "queued" if queued else "subscribed",
                "data_type": "unavailable",
                "candle_source": capabilities(self.contracts[conid])["candle_source"],
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
            self.components_for(conid)
            self.buffered_ticks[conid] = deque(maxlen=200000)
            self._queue_history(conid)
        self.store.put(
            "subscription",
            str(conid),
            {"conid": conid, "contract": self.contracts[conid], "active": True},
        )
        self.store.event("market.subscription.requested", {"conid": conid})
        if "fx_breakout" in capabilities(self.contracts[conid])["executions"]:
            if not self._fx_cache(conid)["sources"]:
                fx_runs = [
                    r
                    for r in self.store.list("run")
                    if self._fx_run(r) and r["conid"] == conid and not r.get("archived")
                ]
                targets = [r for r in fx_runs if r.get("armed") or number(r.get("position", 0))]
                targets = (
                    targets or sorted(fx_runs, key=lambda r: r["created_at"], reverse=True)[:1]
                )
                sources = [r["binding"]["execution_plan"]["signal_source"] for r in targets]
                for source in sources or ["MIDPOINT"]:
                    policy = next(
                        (
                            r["binding"]["execution_plan"]["policy"]
                            for r in targets
                            if r["binding"]["execution_plan"]["signal_source"] == source
                        ),
                        None,
                    )
                    self._fx_prepare_data(conid, source, policy)
            else:
                for source in self._fx_required_sources(conid):
                    self._fx_prepare_data(conid, source)
        return self.data[conid]

    def _queue_history(self, conid, extend=False):
        if "fx_breakout" in capabilities(self.contracts.get(conid, {}))["executions"]:
            self.history_bars.setdefault(conid, {60: {}, 5: {}})
            return
        # Eleven completed exchange sessions plus today's bars. Requests are
        # serialized and paced; they never generate entry decisions.
        stamp = datetime.now(UTC)
        jobs = []
        stock_runs = [
            r
            for r in self.store.list("run")
            if r["conid"] == conid and not r.get("archived") and self._stock_run(r)
        ]
        stock_runs.extend(self.active_preparations(conid))
        if stock_runs and all(premarket(r) for r in stock_runs):
            self._premarket_queue(conid)
            self.history_bars.setdefault(conid, {60: {}, 5: {}})
            return
        stock_runs = [r for r in stock_runs if not premarket(r)]
        contract = self.contracts.get(conid, {})
        if contract.get("stock_rules") and stock_runs:
            from .stock_sessions import stock_calendar

            cal = stock_calendar(contract["stock_rules"]["calendar"])
            needs = [r["binding"]["execution_plan"]["requirements"] for r in stock_runs]
            # Include enough complete sessions for the longest dependency. Short
            # sessions remain valid; incomplete coverage still blocks that input.
            minutes = max(n["lookback_bars"] * n["timeframe"] / 60 for n in needs)
            count = max(
                12 if any(n["reference_sessions"] for n in needs) else 2,
                min(32, 2 + math.ceil(minutes / 120)),
            )
            sessions = cal.sessions_in_range(
                (stamp - timedelta(days=65)).date().isoformat(),
                stamp.astimezone(cal.tz).date().isoformat(),
            )
            for session in sessions[-count:]:
                end = min(cal.session_close(session).to_pydatetime() + timedelta(seconds=1), stamp)
                jobs.append((conid, end.strftime("%Y%m%d-%H:%M:%S"), 60))
        elif self.environment.crypto or capabilities(contract)["session_policy"] == "utc_24x7":
            midnight = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
            for offset in range(11, -1, -1):
                end = min(midnight - timedelta(days=offset) + timedelta(days=1), stamp)
                jobs.append((conid, end.strftime("%Y%m%d-%H:%M:%S"), 60))
        else:
            cal = calendar()
            day = stamp.date().isoformat()
            sessions = cal.sessions_in_range((stamp - timedelta(days=24)).date().isoformat(), day)
            for session in sessions[-12:]:
                if self.legacy_extended_history(conid):
                    from .sessions import candle_bounds

                    close = candle_bounds(cal.session_open(session).to_pydatetime(), True)[1]
                else:
                    close = cal.session_close(session).to_pydatetime()
                end = min(close + timedelta(seconds=1), stamp)
                jobs.append((conid, end.strftime("%Y%m%d-%H:%M:%S"), 60))
        if not stock_runs or any(
            r["binding"]["execution_plan"]["requirements"]["timeframe"] == 5 for r in stock_runs
        ):
            jobs.append((conid, "", 5))
        if extend:
            self.history_contract_jobs[conid] = set(jobs)
            self.history_jobs = [j for j in self.history_jobs if j[0] != conid or j in jobs]
        self.register_history_jobs(jobs)
        self.history_jobs.extend(
            j
            for j in jobs
            if j not in self.history_jobs
            and self.history_units[j]["status"] not in {"pending", "completed"}
        )
        if not extend:
            self.history_bars[conid] = {60: {}, 5: {}}

    def session_bounds(self, stamp):
        return session_bounds(stamp, self.environment.session_policy)

    def unsubscribe(self, conid):
        runs = [r for r in self.store.list("run") if r["conid"] == conid]
        with self.store.transaction() as db:
            dependencies = self._data_dependencies(db)["reasons"].get(conid, [])
            # Submitted work needs positively reconciled terminal outcomes. A
            # never-traded contract has nothing for global reconciliation to prove.
            for run in runs:
                for detail in self._archive_item(db, run["id"])["reasons"]:
                    if not any(d["detail"] == detail for d in dependencies):
                        dependencies.append(
                            {
                                "code": "broker_evidence",
                                "run_id": run["id"],
                                "run_name": run.get("name", run["id"]),
                                "detail": detail,
                                "action": "desk",
                                "remediation": "Inspect this run's orders and reconciliation.",
                            }
                        )
            if dependencies:
                error = Conflict(
                    "Cannot remove this subscription: "
                    + "; ".join(
                        (d.get("run_name") + ": " if d.get("run_name") else "") + d["detail"]
                        for d in dependencies
                    )
                )
                error.dependencies = dependencies
                raise error
            self.broker.unsubscribe(conid)
            self.store.write(db, "subscription", str(conid), {"conid": conid, "active": False})
            self.store.append(db, "market.unsubscribed", {"conid": conid, "dependencies": []})
        self.pending_subscriptions.discard(conid)
        self.history_jobs = [job for job in self.history_jobs if job[0] != conid]
        self.forget_feeds(conid)
        self.data.pop(conid, None)
        getattr(self, "_preparation_dependencies", {}).pop(conid, None)
        self.buffered_ticks.pop(conid, None)
        for run in runs:
            self.runtime.pop(run["id"], None)
        self._retire_data_jobs()
        return {"removed": True}

    def maintain(self):
        if time.monotonic() >= self._next_health_write:
            self.write_health()
            self.monitor_watchdog()
            self.refresh_incidents()
        if self.migration_pending:
            self._next_health_write = time.monotonic() + 2
            self.migration.maintain(self)
            return
        self._finish_removals()
        self._maintain_paper_tests()
        clock = time.monotonic()
        self._maintain_reconciliation(clock)
        if type(self.broker) is PaperGateway and clock >= self._next_acceptance_record:
            self._next_acceptance_record = clock + 60
            observe_session(self)
        self._flush_cancellations()
        self._flush_incident_cancellations()
        while self.history_request_times and clock - self.history_request_times[0] > 600:
            self.history_request_times.popleft()
        if clock >= self._next_health_write:
            self._next_health_write = clock + 2
            active_runs = self.store.list("run")
            self.sleep_guard.set(
                any(r.get("armed") or number(r.get("position", 0)) != 0 for r in active_runs)
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
        if self.broker.overflow.is_set():
            self.invalidate_reconciliation()
            self.incident(
                "callback_overflow",
                "Broker observations overflowed. Reconnect and reconcile before new entries.",
            )
        self._outage_tick()
        if (
            self.requested_connection
            and not self.connected
            and clock >= max(self.next_connect, self.connecting_until)
        ):
            self.next_connect = clock + self.reconnect_delay
            self.reconnect_delay = min(30, self.reconnect_delay * 2)
            try:
                self.broker.disconnect()
                self.broker.connect()
                self.connecting_until = clock + 10
            except Exception:
                self.connecting_until = 0
                self.last_fault = (
                    "Gateway is unavailable or the pinned SDK is missing. Check Settings."
                )
        if self.connected and clock >= self.next_heartbeat:
            self.next_heartbeat = clock + 10
            self.broker.heartbeat()
        if self.connected:
            priority = {p["conid"] for p in self.owned().values() if p["quantity"]}
            for conid in sorted(self.pending_subscriptions, key=lambda c: (c not in priority, c)):
                state = self.data.get(conid, {})
                if state.get("request_state") == "failed" or not self._data_contract_ready(
                    conid, state, clock
                ):
                    continue
                try:
                    subscribed = self.broker.subscribe(conid)
                except Exception as exc:
                    self._data_request_fault(conid, state, exc, "subscription")
                    continue
                if subscribed is not False:
                    self.pending_subscriptions.discard(conid)
                    self.data[conid]["subscription_status"] = "subscribed"
                    if not self.history_bars.get(conid):
                        self._queue_history(conid)
        if self.connected and self.heartbeat_at and clock - self.heartbeat_at > 30:
            self._connection_lost("Gateway heartbeat expired.")
            self.broker.disconnect()
        if self.connected and self.broker.paper_context and clock >= self.next_reconcile:
            self.begin_reconcile()
        self._retire_data_jobs()
        self.maintain_feed_retries(clock)
        self._premarket_maintain(clock)
        for conid, data in self.data.items():
            if (
                self.connected
                and self.contracts.get(conid, {}).get("sec_type") != "CASH"
                and data.get("history_loaded")
                and self.history_complete(conid)
                and not data.get("history_failed")
                and not data.get("warm")
                and conid not in self.repair_requests.values()
                and data.get("repair_after", "z") <= now()
            ):
                job = (conid, "", 60)
                self.register_history_jobs([job])
                unit = self.history_units[job]
                if unit["status"] == "completed":
                    unit.update(status="queued", repair=True)
                if unit["status"] == "queued" and job not in self.history_jobs:
                    unit["repair"] = True
                    self.history_jobs.append(job)
        self._dispatch_history(clock)
        for request, (since, conid) in list(self.history_pending.items()):
            if clock - since > 120:
                if hasattr(self.broker, "cancel_feed"):
                    self.broker.cancel_feed(request)
                self.fail_feed(
                    {
                        "conid": conid,
                        "request": request,
                        "code": 0,
                        "request_kind": "history",
                        "reason": "transient",
                        "parameters": {"use_rth": True},
                    }
                )
                self.store.event("market.history_timeout", {"conid": conid})
        for run in self.store.list("run"):
            if run.get("armed") and run["expires_at"] <= now():
                self.disarm(run["id"], "Session authorization expired.")
        if clock >= self._next_runtime_clock:
            self._next_runtime_clock = clock + 1
            self._credit_maintain()
            self._clock_evaluations()
            self._oca_maintain()
            self._crypto_maintain()
            self._fx_maintain()
            self.resume_authorizations()
        for order in self.store.orders():
            if (
                order["payload"].get("purpose") == "exit"
                and order["payload"].get("exit_type") != "MKT"
                and (
                    order["state"] == "working"
                    or order["state"] == "dispatching"
                    and order["payload"].get("stock_plan", {}).get("session_mode")
                    == "premarket_regular"
                )
            ):
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(order["created_at"])
                ).total_seconds()
                if age > 10 and self.connected and self.attested:
                    self._cancel_known_sell(order["broker_id"])
                    self.store.transition(
                        order["id"], "cancel_pending", {"reason": "exit_limit_refresh"}
                    )
                    self.invalidate_reconciliation()
                    self.next_reconcile = clock + 1
            if (
                not is_pair(order["payload"])
                and order["payload"].get("purpose", "entry") == "entry"
                and order["state"]
                in {
                    "working",
                    "dispatching",
                }
            ):
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(order["created_at"])
                ).total_seconds()
                if age > order["payload"].get("timeout", 30) and self.attested and self.connected:
                    self.cancel_entry(order["id"], reason="entry_timeout")

    def _connection_lost(self, detail):
        self._fx_reset_data()
        if self.connected or self.attested:
            self.incident("connectivity", detail, notify=False)
        self.reconcile_inflight = False
        self._resume_attestation = self._resume_attestation or self.attested
        self.connected = self.attested = self.reconciled = False
        self.clock_ok = False
        self.position_agreement = False
        self.shortable.clear()
        self.connecting_until = 0
        self.next_connect = max(self.next_connect, time.monotonic() + 1)
        for data in self.data.values():
            data["warm"] = False
            data["history_loaded"] = False
            data["live"] = False
            data["repair_after"] = (
                datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1, seconds=2)
            ).isoformat()
        self.history_jobs, self.history_pending, self.repair_requests = [], {}, {}
        self.init_feed_recovery()
        for conid in self.data:
            self.components_for(conid)
        self.history_bars = {}
        self.buffered_ticks = {conid: deque(maxlen=200000) for conid in self.data}
        self.store.event("connection.lost", {"detail": detail})
        for run in self.store.list("run"):
            if run.get("armed"):
                run["armed"] = False
                run.update(state="paused", blocking_reason=detail)
                self.store.put("run", run["id"], run)

    def observe(self, event):
        if not self._snapshot_event_current(event):
            return
        if self.migration_pending:
            return  # The separate data-only collector owns migration observations.
        kind = event["type"]
        if not self.search_observed(event):
            return
        self.restore_archived_observation(event)
        if kind in {
            "tick",
            "quote",
            "quote_size",
            "data_type",
            "realtime_bar",
            "historical_bar",
            "history_end",
        }:
            if hasattr(self.broker, "feed_event_current") and not self.broker.feed_event_current(
                event
            ):
                return
            if event.get("conid") not in self.data:
                return
        if self._fx_data_observation(event):
            return
        if kind != "tick":
            self.feed_observed(event)
        if self._premarket_observation(event):
            return
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
            if self.broker.paper_context and not self._resume_attestation:
                self.verify_paper_context()
                if self.attested:
                    self._restore_subscriptions()
                    self.begin_reconcile()
        elif kind == "account_context":
            self.store.event(
                "paper.context.observed", {"paper": event["paper"], "count": event["count"]}
            )
            if not event["paper"] or event["count"] != 1:
                self.attested = self.reconciled = False
                self.paper_context_token = uuid.uuid4().hex
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
                self.paper_context_token = uuid.uuid4().hex
                self._invalidate_authorizations(
                    "Gateway login context changed. Fresh review is required."
                )
            elif self.connected:
                self.verify_paper_context()
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
            from .rejections import safe_rejection
            from .service_status import known_service

            if (
                event.get("context") == "market_data"
                and hasattr(self.broker, "feed_error_current")
                and not self.broker.feed_error_current(event)
            ):
                event = {**event, "context": "retired_data"}
            code = event["code"]
            if code == 2119:
                self.store.event("broker.service.connecting", {"code": code})
            service = event.get("service") if known_service(event.get("service"), code) else None
            rejection = (
                safe_rejection({**(event.get("rejection") or {}), "code": code})
                if code in {201, 10318}
                else None
            )
            self.store.event(
                "broker.message",
                {
                    "code": code,
                    "request": event["request"],
                    **({"rejection": rejection} if rejection else {}),
                    **({"service": service} if service else {}),
                    **(
                        {"warning": {"code": 399, "category": "unclassified_order_message"}}
                        if code == 399
                        else {}
                    ),
                },
            )
            if code in {2104, 2106, 2158}:
                if not hasattr(self, "_service_recovery"):
                    self._service_recovery = {}
                self._service_recovery[(code, (service or {}).get("farm"))] = {
                    "epoch": self.broker.epoch,
                    "sequence": self.incidents.watermark(),
                }
            if code == 399 and self._fx_record_warning(event):
                return
            owned_rejection = (
                code in {201, 10318}
                and (code != 10318 or self._initial_quantity_rejection(event["request"]))
                and event.get("context") in {None, "broker"}
                and any(event["request"] in order_ids(o) for o in self.store.orders())
            )
            if (
                code == 10147
                and (self.store.get("broker_order", str(event["request"])) or {}).get(
                    "rejection_code"
                )
                == 10318
            ):
                return  # A not-found response cannot overwrite a conclusive validation rejection.
            if owned_rejection and code == 10318:
                self._record_quantity_rejection(event["request"])
            if owned_rejection:
                prior = self.store.get("broker_order", str(event["request"])) or {}
                if not rejection["available"] and (prior.get("rejection") or {}).get("available"):
                    rejection = safe_rejection(prior["rejection"])
                rejected = {
                    "broker_id": event["request"],
                    "client_id": self.broker.client_id,
                    "status": "Rejected",
                    "rejection_code": code,
                    "rejection": rejection,
                }
                projected = self._order_observation(rejected)
                self.broker_orders[event["request"]] = {
                    **self.broker_orders.get(event["request"], {}),
                    **rejected,
                    # An error callback is not fresh order identity evidence.
                    # Retain reducer state without importing old-session details.
                    **{
                        key: value
                        for key, value in (projected or {}).items()
                        if key in {"status", "filled", "remaining", "average", "status_conflict"}
                    },
                }
            if code in {1100, 1300, 502, 504}:
                self._connection_lost("Gateway connectivity interrupted.")
            elif code in {1101, 1102}:
                self.invalidate_reconciliation()
                for conid in self.data:
                    self._data_gap(
                        conid,
                        "Gateway data recovery requires history repair.",
                        routine_recovery=True,
                    )
                if code == 1101:
                    self.broker.reset_subscriptions()
                    for conid in self.data:
                        for component in ("quote", "trade"):
                            self.components_for(conid)[component].update(
                                status="pending",
                                retry_at=None,
                                manual_pending=False,
                            )
                    self.pending_subscriptions.update(self.data)
                if self.attested:
                    self.begin_reconcile()
            elif event.get("context") in {"market_data", "search"} and code not in {
                2104,
                2106,
                2107,
                2108,
                2158,
                2109,
                2119,
            }:
                self.fail_feed(event)
                self.store.event(
                    "market.diagnostic",
                    {
                        "conid": event.get("conid"),
                        "code": code,
                        "reason": event.get("reason", "unknown"),
                        "request_kind": event.get("request_kind", "unknown"),
                    },
                )
            elif event.get("context") == "retired_data":
                self.store.event(
                    "market.retired_request.diagnostic",
                    {
                        "conid": event.get("conid"),
                        "code": code,
                        "reason": event.get("reason", "unknown"),
                        "request": event["request"],
                        "generation": event.get("generation"),
                    },
                )
            elif event.get("context") == "pnl" and not any(
                event["request"] in order_ids(o) for o in self.store.orders()
            ):
                self.pnl_diagnostic = f"Optional P/L subscription returned code {code}."
                self.store.event("pnl.diagnostic", {"code": code})
            elif event.get("context") in {"account_snapshot", "retired_search"}:
                self.store.event(
                    "broker.request.diagnostic", {"code": code, "context": event["context"]}
                )
            elif code not in {2104, 2106, 2107, 2108, 2158, 2109, 2119} and not owned_rejection:
                execution = next(
                    (o for o in self.store.orders() if event["request"] in order_ids(o)), None
                )
                if code not in {2103, 2105, 2157, 2110}:
                    if execution:
                        self.invalidate_reconciliation()
                        self.incident(
                            "order_uncertain",
                            f"Broker code {code} affects a submitted order; reconcile its outcome.",
                            order_context={
                                "order_id": execution["id"],
                                "run_id": execution["run_id"],
                                "broker_id": event["request"],
                            },
                            diagnostic={"code": code, "context": "execution"},
                        )
                    elif code in {201, 202}:
                        self.invalidate_reconciliation()
                        self.incident(
                            f"broker_{code}",
                            "An uncorrelated order outcome requires reconciliation.",
                            diagnostic={"code": code, "context": "execution"},
                        )
                    else:
                        from .diagnostics import broker_diagnostic

                        safe_diagnostic = broker_diagnostic(
                            code,
                            "Read-Only mode"
                            if (event.get("diagnostic") or {}).get("reason") == "api_read_only"
                            else "",
                        )
                        self.incident(
                            "broker_notice",
                            safe_diagnostic["detail"]
                            if code == 321
                            else f"Broker notification {code}; "
                            "no submitted order is associated with this request.",
                            diagnostic={
                                "code": code,
                                "context": event.get("context", "broker"),
                                **({"reason": safe_diagnostic["reason"]} if code == 321 else {}),
                            },
                            correlation_key=f"code:{code}",
                            notify=False,
                        )
                    return
                self.service_incident(
                    f"broker_{code}",
                    f"Gateway code {code}: inspect diagnostics. Affected actions are blocked.",
                    **(
                        {
                            "diagnostic": service,
                            "correlation_key": "farm:" + service["farm"].replace(".", "_"),
                        }
                        if service
                        else {}
                    ),
                )
        elif kind == "contract_candidate":
            if event["conid"] not in self.contracts or not self.contracts[event["conid"]].get(
                "resolved", True
            ):
                self.contracts[event["conid"]] = {
                    k: v for k, v in event.items() if k not in {"type", "epoch"}
                }
        elif kind == "contract":
            self.contracts[event["conid"]] = {
                k: v for k, v in event.items() if k not in {"type", "epoch"}
            }
            self.contracts[event["conid"]].update(
                metadata_instance=self.process_identity,
                metadata_epoch=self.broker.epoch,
                metadata_received_at=now(),
            )
            saved_rules = self.store.get("stock_rules", str(event["conid"]))
            if saved_rules:
                self.contracts[event["conid"]]["stock_rules"] = saved_rules
            self._resolve_stock_rules(event["conid"])
            self.contracts[event["conid"]]["capabilities"] = capabilities(
                self.contracts[event["conid"]]
            )
            if self.environment.crypto:
                self.broker.set_contract(self.contracts[event["conid"]])
            if event["conid"] in self._data_dependencies()["contracts"]:
                self.subscribe(event["conid"])
        elif kind == "market_rule":
            self.market_rules[event["rule"]] = event["increments"]
            if not hasattr(self, "_stock_market_rule_context"):
                self._stock_market_rule_context = {}
            self._stock_market_rule_context[event["rule"]] = (
                self.process_identity,
                self.broker.epoch,
            )
        elif kind == "shortable":
            self.shortable[event["conid"]] = {"quantity": event["quantity"], "received_at": now()}
        elif kind == "credit_preview":
            self._credit_observe(event)
        elif kind == "short_preview":
            for run in self.store.list("run"):
                preview = self.store.get("oca_credit", run["id"]) or {}
                if preview.get("broker_id") == event["broker_id"]:
                    preview.update(status=event["status"], received_at=now())
                    self.store.put("oca_credit", run["id"], preview)
                    self.store.event("oca.short_credit.observed", {"run_id": run["id"], **preview})
        elif kind == "fx_quote":
            self._stock_fx(event)
        elif kind == "account_fact":
            self._snapshot_account_fact(event)
        elif kind == "daily_pnl":
            try:
                self.daily_pnl = number(event["daily"])
                self.pnl_at = clock
                self.pnl_received_at = now()
                self.pnl_diagnostic = None
            except GraphError:
                self.daily_pnl = None
        elif kind == "position":
            if not event["own_account"]:
                self.incident(
                    "foreign_account", "Reconciliation observed an unexpected account context."
                )
            self._snapshot_position(event)
        elif kind == "open_order":
            prior = self.store.get("broker_order", str(event["broker_id"])) or {}
            if event.get("status") == "Inactive" and prior.get("rejection_code") in {201, 10318}:
                event["status"] = "Rejected"
            if event.get("completed") and event.get("reference", "").startswith("oms-"):
                intent = next(
                    (o for o in self.store.orders() if "oms-" + o["id"] == event["reference"]), None
                )
                if intent:
                    if is_pair(intent["payload"]):
                        direction = "long" if event.get("action") == "BUY" else "short"
                        purpose = "entry"
                        if event.get("parent_id", 0):
                            direction = "short" if direction == "long" else "long"
                            purpose = "stop"
                        event["broker_id"] = intent["payload"]["leg_ids"][direction + "_" + purpose]
                    else:
                        self._map_completed_legacy(event, intent)
            key = (
                event["broker_id"]
                if event["client_id"] == self.broker.client_id
                else f"external-{event['client_id']}-{event['broker_id']}"
            )
            projected = self._order_observation(event)
            self.broker_orders[key] = projected or {**self.broker_orders.get(key, {}), **event}
            self._snapshot_order(key, self.broker_orders[key])
            self._fx_order_account_evidence(event)
            self._fx_confirm_warning(event["broker_id"], self.broker_orders[key])
        elif kind == "order_status":
            prior = self.store.get("broker_order", str(event["broker_id"])) or {}
            if event.get("status") == "Inactive" and prior.get("rejection_code") in {201, 10318}:
                event["status"] = "Rejected"
            key = (
                event["broker_id"]
                if event["client_id"] == self.broker.client_id
                else f"external-{event['client_id']}-{event['broker_id']}"
            )
            current = {
                **self.broker_orders.get(key, {}),
                **event,
            }
            projected = self._order_observation(event)
            # Only full open/completed-order callbacks establish current snapshot
            # identity. Reuse the reducer's lifecycle, not old-session identity fields.
            if projected:
                for field in ("status", "filled", "remaining", "average", "status_conflict"):
                    if field in projected:
                        current[field] = projected[field]
                    else:
                        current.pop(field, None)
            self.broker_orders[key] = current
            self._snapshot_order(key, current)
            self._fx_confirm_warning(event["broker_id"], current)
        elif kind == "execution":
            self._execution(event)
            self._crypto_sync()
            self._stock_sync()
            for run in self.store.list("run"):
                if self._fx_run(run):
                    self._fx_sync(run)
        elif kind == "commission":
            previous = self.store.get("commission", event["execution_id"])
            self.store.put(
                "commission",
                event["execution_id"],
                {**event, "received_at": (previous or {}).get("received_at", now())},
            )
            self.store.event("execution.commission", event)
            if previous is None or any(
                previous.get(k) != event.get(k) for k in ("currency", "amount")
            ):
                if any(self._fx_run(r) for r in self.store.list("run")):
                    self.invalidate_reconciliation()
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
            self.data[event["conid"]].update(
                live=event["live"],
                data_type=event.get("data_type", "live" if event["live"] else "unavailable"),
            )
        elif kind == "quote_size" and event["conid"] in self.data:
            self.data[event["conid"]].setdefault("sizes", {})[event["side"]] = {
                "value": event["value"],
                "received_at": event.get("received_at", now()),
            }
        elif kind == "quote":
            self.quotes.setdefault(event["conid"], {})[event["side"]] = {
                "price": event["price"],
                "received_at": event.get("received_at", now()),
                "capture": event.get("capture"),
            }
        elif kind == "realtime_bar":
            bars = self.display_bars.setdefault(event["conid"], {})
            bars[event["timestamp"]] = event
            if len(bars) > 3600:
                del bars[min(bars, key=int)]
        elif kind == "historical_bar":
            bars = self.history_bars.get(event["conid"])
            if bars is not None:
                bars[event["seconds"]][event["timestamp"]] = event
        elif kind == "history_end":
            self.history_finished(event["request"])
            self.history_pending.pop(event["request"], None)
            repairing = self.repair_requests.pop(event["request"], None) is not None
            conid = event["conid"]
            if (
                conid in self.data
                and self.history_complete(conid)
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
                self.data[conid]["history_failed"] = False
                self.data[conid]["history_loaded"] = True
                self.data[conid]["capture"] = manifest
                self._history_summary(conid)
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
                        if premarket(run) or not self._requires_downloaded_history(run):
                            continue
                        if run.get("conid") == conid and (
                            self.environment.crypto or not run.get("capability_error")
                        ):
                            self._runtime(run, reset=True)
                    self.store.event(
                        "market.warmup.finished",
                        {"conid": conid, "capture": manifest, "retrospective_entries": False},
                    )
        elif kind == "tick":
            self._tick(event)
        if self.environment.crypto and kind in {"quote", "tick", "data_type"}:
            self.broker.on_market(event)

    def _finish_reconcile(self):
        if not self._publish_snapshot():
            return
        self.reconcile_inflight = False
        self._reconcile_quantity_rejections()
        from .fx_order_evidence import record

        for key, observed in self.broker_orders.items():
            if isinstance(key, int):
                record(self.store, {"broker_id": key}, observed)
                self._fx_confirm_warning(key, observed)
        for order in self.store.orders():
            if is_pair(order["payload"]):
                self._oca_sync(order)
        identity_issues = self._identity_issues()
        identity_issues.extend(self._fill_agreement_issues())
        issues = list(identity_issues)
        owned = self.owned()
        self._crypto_sync()
        self._stock_sync()
        for run in self.store.list("run"):
            if self._fx_run(run):
                self._fx_sync(run)
        fx_issues = self._fx_cash_issues()
        issues.extend(fx_issues)
        credit_issues = self._credit_account_issues()
        issues.extend(credit_issues)
        if credit_issues and not getattr(self, "_credit_shortfall", False):
            self.incident("broker_credit_shortfall", credit_issues[0])
        self._credit_shortfall = bool(credit_issues)
        if fx_issues and fx_issues != ["FX commissions are awaiting broker evidence."]:
            signature = digest(fx_issues)
            if getattr(self, "_fx_balance_failure", None) != signature:
                self.incident("fx_account_balance", " ".join(fx_issues))
                self._fx_balance_failure = signature
        elif not fx_issues:
            self._fx_balance_failure = None
        security_owned = {
            k: p for k, p in owned.items() if not self._fx_run(self.store.get("run", k))
        }
        managed_positions = {
            k: p for k, p in self.positions.items() if not self._currency_position(p)
        }
        expected_types = {"CRYPTO"} if self.environment.crypto else {"STK", "CRYPTO"}
        if any(
            number(p.get("quantity", 0)) and p.get("sec_type") not in expected_types
            for p in managed_positions.values()
        ):
            issues.append(
                "A position has an unexpected instrument type. Request a fresh typed snapshot."
            )
        if any(p.get("own_account") is False for p in self.positions.values()):
            issues.append("An unexpected account position was observed.")
        self._reconcile_cancellations()
        issues.extend(self._flat_sell_issues(owned))
        self.position_agreement = (
            all(
                sum(
                    (p["quantity"] for p in security_owned.values() if p["conid"] == conid),
                    Decimal(0),
                )
                == number(managed_positions.get(conid, {}).get("quantity", 0))
                for conid in {p["conid"] for p in security_owned.values()} | set(managed_positions)
            )
            and not fx_issues
        )
        totals = {}
        for position in owned.values():
            if position["run_id"] in security_owned:
                totals[position["conid"]] = (
                    totals.get(position["conid"], Decimal(0)) + position["quantity"]
                )
            entry = next(o for o in self.store.orders() if o["id"] == position["entry_id"])
            if position["quantity"] < 0 and not is_pair(entry["payload"]):
                issues.append("An owned position has a negative quantity.")
            if position["quantity"] != 0:
                entry = next(o for o in self.store.orders() if o["id"] == position["entry_id"])
                valid = (
                    (
                        self.position_agreement
                        or self._fx_run(self.store.get("run", position["run_id"]))
                        and self._fx_ownership_agrees(self.store.get("run", position["run_id"]))
                    )
                    and not identity_issues
                    and self._valid_protection(position, entry)
                )
                if self._fx_run(self.store.get("run", position["run_id"])):
                    # This stop's health is independent of unrelated order errors.
                    valid = self._fx_valid_protection(position, entry)
                position["protected"] = valid
                if not valid:
                    issues.append("An owned position lacks verified active protection.")
                    if (
                        entry["payload"].get("execution") != "crypto_breakout"
                        and not self._stock_provisional(position, entry)
                        and not self._fx_provisional(position, entry)
                        and not (
                            is_pair(entry["payload"]) and self._oca_provisional(position, entry)
                        )
                    ):
                        self.incident(
                            "missing_protection",
                            "An owned position lacks verified active protection. "
                            "Cancel the remaining entry and inspect Gateway immediately.",
                        )
                    if not identity_issues:
                        self._repair_protection(position, entry)
        for conid in set(totals) | set(managed_positions):
            if totals.get(conid, Decimal(0)) != number(
                managed_positions.get(conid, {}).get("quantity", 0)
            ):
                issues.append(
                    "Local and broker positions disagree, or external positions are present."
                )
        if any(o["state"] in {"unknown", "dispatching"} for o in self.store.orders()):
            issues.append("An order outcome remains uncertain.")
        if any(o["state"] == "cancel_pending" for o in self.store.orders()):
            issues.append("An order cancellation awaits broker confirmation.")
        if not {"NetLiquidation", "AvailableFunds", "GrossPositionValue"} <= set(self.facts):
            issues.append("Required USD account facts are missing.")
        self.reconciled = not issues
        self.reconciled_at = time.monotonic()
        self.reconciliation_evidence = {
            **(self._reconciliation_started or {}),
            "completed_at": now(),
            "ready": self.reconciled,
        }
        self.last_fault = " ".join(dict.fromkeys(issues)) or None
        if self.reconciled:
            with self.store.transaction() as db:
                for order in self.store.orders():
                    position = owned.get(order["run_id"])
                    reservation = self.store.read(db, "reservation", order["id"])
                    children = [
                        self.broker_orders.get(i, {})
                        for i in order_ids(order) - {order["broker_id"]}
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
            if position and position["quantity"] != 0:
                if run.get("archived"):
                    run.update(
                        archived=False, removal_pending=False, armed=False, late_fill_recovery=True
                    )
                    self.incident(
                        "late_archived_fill",
                        "A removed run received a late fill; reconcile ownership and protection.",
                        run=run,
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
            if (
                run.get("armed")
                and self.reconciled
                and not (position and position["quantity"] != 0)
            ):
                pending = any(
                    o["run_id"] == run["id"]
                    and o["payload"].get("purpose", "entry") == "entry"
                    and o["state"] not in {"filled", "cancelled", "rejected"}
                    for o in self.store.orders()
                )
                run.update(
                    state="entry_working"
                    if pending
                    else "waiting_session"
                    if run.get("valid_from", "") > now()
                    else "armed",
                    blocking_reason=None,
                )
                self.store.put("run", run["id"], run)
            if not position or position["quantity"] == 0:
                if self.store.get("exit_request", run["id"]):
                    self.store.put("exit_request", run["id"], {})
        self.store.event(
            "reconciliation.finished",
            {
                "recovery_evidence": self.reconciliation_evidence,
                "ready": self.reconciled,
                "issues": issues,
                "positions": list(self.positions.values()),
                "account_facts": self.facts,
                "broker_orders": list(self.broker_orders.values()),
            },
        )
        self._oca_reconciled()
        self._crypto_reconciled()
        self._stock_reconciled()
        self._fx_settle_reservations()
        if self.reconciled and type(self.broker) is PaperGateway:
            evidence = self.store.get("qualification", "broker_evidence") or {}
            for position in owned.values():
                key = position["run_id"]
                trial_run = self.store.get("run", key) or {}
                if trial_run.get("execution") == "crypto_breakout" or trial_run.get(
                    "diagnostic_test"
                ):
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

    @staticmethod
    def _map_completed_legacy(event, intent):
        if intent["payload"].get("execution") == "fx_breakout":
            event["broker_id"] = intent["broker_id"]
            return
        offset = 0
        if intent["payload"].get("purpose", "entry") == "entry" and event.get("action") == "SELL":
            offset = 2 if event.get("order_type") == "STP" else 1
        event["broker_id"] = intent["broker_id"] + offset

    def readiness(self, runs=None):
        critical = self.incidents.applicable(runs)
        migration = (
            [
                check(
                    "workspace_migration",
                    "Workspace migration complete",
                    False,
                    self.migration.detail,
                )
            ]
            if self.migration_pending
            else []
        )
        watchdog = self.watchdog_status()
        checks = migration + [
            check(
                "watchdog", "Independent watchdog running", watchdog["ready"], watchdog["detail"]
            ),
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
                "The adapter automatically verifies the paper account after the handshake.",
            ),
            check(
                "reconciliation",
                "Orders and positions reconciled",
                self.reconciled and time.monotonic() - self.reconciled_at < 30,
                self.last_fault or self.reconciliation_progress()["detail"],
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
                "Current trading concerns",
                not critical,
                "; ".join(i["detail"] for i in critical)
                if critical
                else "No current concerns affect this selection.",
                "/activity",
            ),
            check(
                "broker_funds",
                "Broker account facts",
                number(self.facts.get("AvailableFunds", 0)) > 0
                and (
                    runs is None
                    or all(
                        (r.get("binding") or {}).get("execution_plan", {}).get("risk_policy")
                        == "paper_stock_v2"
                        for r in (runs or [])
                    )
                    and bool(runs)
                    or number(self.facts.get("GrossPositionValue", 5001)) <= 5000
                ),
                "Verified available funds and the selected risk-policy checks are required.",
            ),
        ]
        progressing = (
            {"reconciliation"} if self.reconcile_inflight and not self.last_fault else set()
        )
        if self.requested_connection and not self.connected:
            progressing.update({"gateway", "sdk_compatibility", "paper_context", "clock"})
        for item in checks:
            item["evidence_revision"] = getattr(self, "_evidence_revision", 0)
            if not item["passed"] and item["code"] in progressing:
                item.update(status="checking", category="progress", remediation=None)
        return checks

    @staticmethod
    def _currency_position(position):
        return (
            position.get("sec_type") == "CASH"
            and position.get("own_account") is True
            and bool(position.get("currency"))
        )

    def pnl_status(self):
        age = max(0, time.monotonic() - self.pnl_at) if self.pnl_received_at else None
        return {
            "value": str(self.daily_pnl) if self.daily_pnl is not None else None,
            "currency": self.pnl_currency,
            "received_at": self.pnl_received_at,
            "age_seconds": age,
            "status": "unavailable"
            if self.daily_pnl is None
            else "stale"
            if age is None or age >= 30 or not self.connected
            else "current",
            "informational": True,
            "diagnostic": self.pnl_diagnostic,
        }

    def _history_summary(self, conid):
        bars = self.history_bars.get(conid, {60: {}, 5: {}})
        days = {}
        contract = self.contracts.get(conid, {})
        schedule = StockSession(contract) if contract.get("stock_rules") else None
        for raw in bars[60]:
            stamp = datetime.fromtimestamp(int(raw), UTC)
            bounds = (
                schedule.bounds(stamp)
                if schedule
                else session_bounds(
                    stamp, capabilities(self.contracts.get(conid, {}))["session_policy"]
                )
            )
            if bounds and bounds[0] <= stamp < bounds[1] and bounds[1] <= datetime.now(UTC):
                key = bounds[0].isoformat()
                if key not in days:
                    days[key] = (
                        set(),
                        len(schedule.minutes(stamp))
                        if schedule
                        else int((bounds[1] - bounds[0]).total_seconds() // 60),
                    )
                minutes, expected = days[key]
                minutes.add(int((stamp - bounds[0]).total_seconds() // 60))
        self.data[conid]["history_progress"] = {
            "minute_bars": len(bars[60]),
            "fine_bars": len(bars[5]),
            "complete_reference_sessions": min(
                10, sum(len(minutes) == expected for minutes, expected in days.values())
            ),
            "required_reference_sessions": max(
                (
                    r["binding"]["execution_plan"]["requirements"]["reference_sessions"]
                    for r in self.store.list("run")
                    if r["conid"] == conid and self._stock_run(r)
                ),
                default=0,
            )
            if schedule
            else 10,
        }

    def data_snapshot(self, include_candles=True):
        result = []
        for conid, data in self.data.items():
            item = copy.deepcopy(data)
            if conid in getattr(self, "fx_data", {}):
                result.append(self._fx_data_view(conid, item))
                continue
            item["currency"] = self.contracts.get(conid, {}).get("currency", "USD")
            item["price_scale"] = (
                self.contracts.get(conid, {}).get("stock_rules", {}).get("price_scale", "1")
            )
            item["capabilities"] = capabilities(self.contracts.get(conid, {}))
            if include_candles:
                item["candles"] = self._display_candles(conid)
            item["quotes"] = copy.deepcopy(self.quotes.get(conid, {}))
            fresh = (
                data.get("received_at")
                and data.get("source_at")
                and (
                    datetime.now(UTC) - datetime.fromisoformat(data["received_at"])
                ).total_seconds()
                <= 15
                and abs(
                    (datetime.now(UTC) - datetime.fromisoformat(data["source_at"])).total_seconds()
                )
                <= 15
            )
            bounds = session_bounds(
                datetime.now(UTC), capabilities(self.contracts.get(conid, {}))["session_policy"]
            )
            market_open = bool(bounds and bounds[0] <= datetime.now(UTC) < bounds[1])
            if self.contracts.get(conid, {}).get("stock_rules"):
                market_open = StockSession(self.contracts[conid]).tradable(datetime.now(UTC))
            item["feed_status"] = (
                "fresh" if fresh else "market_closed" if not market_open else "waiting_for_trades"
            )
            item["history_status"] = (
                "failed"
                if data.get("history_failed")
                else "loaded"
                if data.get("history_loaded")
                else "loading"
            )
            item["components"] = self.feed_projection(conid)
            extended = getattr(self, "premarket_history", {}).get(conid)
            if extended:
                item["extended_history"] = {
                    "status": extended["status"],
                    "detail": extended.get("detail"),
                    "minute_bars": len(extended["bars"][60]),
                    "retry_available": extended["status"] == "failed",
                    **request_progress([extended]),
                }
            if item["components"].get("trade", {}).get("status") == "failed":
                item["feed_status"] = "trade_feed_rejected"
            contexts = sorted(
                (
                    r
                    for r in self.store.list("run")
                    if r["conid"] == conid and not r.get("archived") and self._stock_run(r)
                ),
                key=lambda r: (bool(r.get("armed")), r.get("created_at", "")),
                reverse=True,
            )
            context = contexts[0] if contexts else None
            if context:
                market_open = self._stock_session(context).tradable(datetime.now(UTC))
                item["session_mode"] = "premarket_regular" if premarket(context) else "regular"
                item["session_open"] = market_open
                item["run_id"] = context["id"]
                if item["feed_status"] != "trade_feed_rejected":
                    item["feed_status"] = (
                        "fresh"
                        if fresh and market_open
                        else "market_closed"
                        if not market_open
                        else "waiting_for_trades"
                    )
            item.update(self.feed_health(conid, context))
            item["ready"] = item["execution_fresh"] and market_open
            result.append(item)
        return result

    def overview(self):
        cached = getattr(self, "_overview_cache", None)
        if cached and time.monotonic() - cached[0] < 1:
            return cached[1]
        result = copy.deepcopy(self.snapshot(compact=True))
        self._overview_cache = (time.monotonic(), result)
        return result

    def snapshot(self, compact=False):
        checks = self.readiness([])
        incident_page = self.incidents.page()
        runs = self.store.display_runs() if compact else self.store.list("run")
        run_ids = {r["id"] for r in runs}
        orders = [
            {**o, "diagnostics": self.order_diagnostics(o)}
            for o in self.store.orders(active_only=compact)
        ]

        def visible_run(run):
            if self.migration_pending:
                return {
                    **run,
                    "armed": False,
                    "state": "paused",
                    "blocking_reason": self.migration.detail,
                }
            run = self._signal_run_view(run)
            if self._fx_run(run) and self.owned().get(run["id"], {}).get("quantity"):
                protection = self._fx_protection_assessment(run)
                run = {
                    **run,
                    "protected": protection["state"] == "active",
                    "protection_verification": protection,
                }
            if (
                run.get("armed")
                and run.get("state") == "armed"
                and not run.get("signal_outcome")
                and not self._run_feed_health(run)["execution_fresh"]
            ):
                return {
                    **run,
                    "display_state": "Armed — waiting for fresh FX quotes"
                    if self._fx_run(run)
                    else "Armed — waiting for fresh trades",
                    "blocking_reason": self._run_feed_health(run)["execution_detail"],
                }
            return run

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
            "watchdog": self.watchdog_status(),
            "build": getattr(self, "build", None),
            "migration": self.migration.snapshot() if self.migration else None,
            "mode": self.environment.mode,
            "environment": self.environment.name,
            "data_source": self.environment.data_source,
            "execution_provider": self.environment.execution_provider,
            "session_policy": self.environment.session_policy
            if self.environment.crypto
            else "per_contract",
            "simulation_assumptions": [
                "Local full fills at subsequent eligible quotes",
                "Zero fees; no queue or liquidity model",
                "Local simulated protection; no broker orders",
                "Hypothetical cash-secured shorts; no borrow costs or leverage",
            ]
            if self.environment.crypto
            else [],
            "outage": self.store.get("connection_outage", "current"),
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
                and self._run_feed_health(r)["execution_fresh"]
                and self._session_permission(r)
                and not self.incidents.applicable([r])
                for r in self.store.list("run")
            ),
            "emergency": self.store.emergency(),
            "checks": checks,
            "runs": [visible_run(run) for run in runs],
            "orders": orders,
            "oca_groups": [
                {
                    **g,
                    **self._stock_display_units(g["run_id"]),
                }
                for g in self._oca_groups()
                if not compact or g.get("run_id") in run_ids
            ],
            "crypto_triggers": [
                t
                for t in self.store.list("crypto_trigger")
                if not compact or t.get("run_id") in run_ids
            ],
            "stock_triggers": [
                t
                for t in self.store.list("stock_trigger")
                if not compact or t.get("run_id") in run_ids
            ],
            "stock_protection": self._stock_protection_view(run_ids if compact else None),
            "fx_protection": self._fx_protection_view(run_ids if compact else None),
            "local_protection": [
                {
                    **p,
                    "status": "active"
                    if self._crypto_valid_protection(
                        self.owned().get(
                            p["run_id"],
                            {
                                "run_id": p["run_id"],
                                "conid": 0,
                                "entry_id": "",
                                "quantity": Decimal(0),
                            },
                        )
                    )
                    else "suspended"
                    if number(p.get("quantity", 0)) > 0
                    else "closed",
                }
                for p in self.store.list("crypto_protection")
                if not compact or p.get("run_id") in run_ids
            ],
            "positions": [
                {**p, "quantity": str(p["quantity"]), "cash": str(p["cash"])}
                for p in self.owned().values()
                if not compact or p["quantity"] != 0
            ],
            "broker_positions": list(self.positions.values()),
            "currency_positions": [
                p for p in self.positions.values() if self._currency_position(p)
            ],
            "reconciliation": {
                **self.reconciliation_progress(),
                "ready": self.reconciled,
                "detail": self.last_fault
                or (
                    self.reconciliation_progress()["detail"]
                    if self.reconcile_inflight
                    else self._position_summary()
                ),
                "in_progress": self.reconcile_inflight,
                "evidence_revision": getattr(self, "_evidence_revision", 0),
                "verified_revision": (self.reconciliation_evidence or {}).get("evidence_revision"),
                "age_seconds": max(0, time.monotonic() - self.reconciled_at)
                if self.reconciliation_evidence
                else None,
            },
            "pnl": self.pnl_status(),
            "data": self.data_snapshot(include_candles=not compact),
            "contracts": list(self.contracts.values()),
            "incidents": incident_page["items"] if compact else self.store.list("incident"),
            "incident_counts": self.incidents.counts(),
            "incident_next_cursor": incident_page["next_cursor"],
            "account_facts": dict(self.facts),
            "timestamp": now(),
            "evaluations": evaluations,
        }

    def _position_summary(self):
        currencies = sum(self._currency_position(p) for p in self.positions.values())
        securities = sum(
            bool(number(p.get("quantity", 0)))
            for p in self.positions.values()
            if not self._currency_position(p)
        )
        return f"{securities} security positions; {currencies} currency positions reported."

    def order_detail(self, identity):
        order = next((o for o in self.store.orders() if o["id"] == identity), None)
        if not order:
            raise ValueError("Order not found.")
        run = self.store.get("run", order["run_id"])
        if self._fx_run(run):
            protection = self._fx_protection_assessment(run)
            run = {
                **run,
                "protected": protection["state"] == "active",
                "protection_verification": protection,
            }
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
                    "FROM events WHERE json_extract(payload,'$.run_id')=? "
                    "OR json_extract(payload,'$.id')=? "
                    "OR json_extract(payload,'$.order_id')=? ORDER BY sequence DESC LIMIT 200",
                    (order["run_id"], identity, identity),
                )
            ]
        return {
            "order": {**order, "diagnostics": self.order_diagnostics(order)},
            "stock_protection": self.store.get("stock_protection", order["run_id"]),
            "fx_protection": self.store.get("fx_protection", order["run_id"]),
            "fx_allocation": self._fx_allocation(run),
            "commissions": [self.store.get("commission", e["execution_id"]) for e in executions],
            "run": run,
            "executions": executions,
            "broker_observations": [
                self.store.get("broker_order", str(key)) for key in order_ids(order)
            ],
            "timeline": timeline,
        }

    def _build_run(
        self,
        strategy_id,
        version,
        conid,
        sizing=None,
        protection_type="broker_held",
        execution_plan_revision=None,
        session_mode="regular",
        funding_policy=None,
        execution_policy=None,
    ):
        from .library import require_available

        with self.store.connect() as db:
            require_available(self.store, db, strategy_id)
        published = self.store.version(strategy_id, version)
        if session_mode != "regular" and published["document"]["schema_version"] not in (7, 8, 9):
            raise Conflict("Pre-market execution requires an explicitly bound schema-7 stock run.")
        crypto_graph = published["document"]["settings"].get("instrument_profile") == "paxos_crypto"
        if (
            published["document"]["schema_version"] not in {6, 7, 8, 9}
            and crypto_graph != self.environment.crypto
        ):
            raise Conflict(
                "The strategy instrument profile must match this execution environment. "
                "Import a converted copy first."
            )
        if conid not in self.contracts:
            raise ValueError("Resolve and select a Gateway contract in Settings first.")
        symbol = self.contracts[conid]["symbol"]
        if (
            published["document"]["schema_version"] not in {6, 7, 8, 9}
            and symbol != published["document"]["settings"]["symbol"]
        ):
            raise ValueError("The resolved symbol must match the published strategy symbol.")
        if self.contracts[conid].get("resolved") is False:
            raise ValueError("Resolve the full contract identity before preparing a run.")
        binding = None
        if published["document"]["schema_version"] == 6:
            binding = {
                "contract": copy.deepcopy(self.contracts[conid]),
                "sizing": reviewed_sizing(published["document"], sizing),
                "strategy_hash": published["hash"],
                "session_policy": capabilities(self.contracts[conid])["session_policy"],
            }
            binding["hash"] = digest(binding)
        elif published["document"]["schema_version"] == 9:
            if self.environment.crypto or session_mode != "fx":
                raise Conflict("Schema-9 FX runs require the paper FX session policy.")
            binding = self._fx_binding(
                published,
                conid,
                sizing,
                protection_type,
                execution_plan_revision,
                funding_policy,
                execution_policy,
            )
        elif published["document"]["schema_version"] in (7, 8):
            if self.environment.crypto:
                raise Conflict("Schema-7 stock runs require the IBKR paper workspace.")
            binding = self._stock_binding(
                published,
                conid,
                sizing,
                protection_type,
                execution_plan_revision,
                session_mode,
                funding_policy,
            )
        elif sizing:
            raise ValueError(
                "Legacy sizing is part of the published strategy. Convert a reusable copy first."
            )
        if funding_policy is not None and (not binding or not binding.get("execution_plan")):
            raise Conflict("Broker credit requires a supported reusable stock or FX binding.")
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
            "risk": binding["sizing"]["risk"]
            if binding
            else published["document"]["settings"]["risk"],
            "created_at": now(),
            "blocking_reason": "Review the session before arming.",
            "execution": execution_kind(published["document"]),
            "binding": binding,
            "protection_type": capabilities(self.contracts[conid])["protection_type"],
            "capability_error": execution_reason(self.contracts[conid], published["document"]),
            "session_policy": capabilities(self.contracts[conid])["session_policy"],
        }
        if binding and binding.get("execution_plan"):
            plan = binding["execution_plan"]
            run.update(
                protection_type=plan["protection_type"],
                session_policy=plan["session_policy"],
                capability_error=None,
                currency=plan["currency"],
            )
        return run

    def create_run(self, *args, **kwargs):
        from .credit_policy import ensure_policy
        from .library import require_available

        run = self._build_run(*args, **kwargs)
        plan = (run.get("binding") or {}).get("execution_plan") or {}
        if plan.get("funding_policy"):
            ensure_policy(self.store, plan["funding_policy"])
        with self.store.transaction() as db:
            strategy_id, version = run["strategy_id"], run["version"]
            require_available(self.store, db, strategy_id)
            self.store.write(db, "run", run["id"], run)
            self.store.append(
                db,
                "run.created",
                {"run_id": run["id"], "strategy_id": strategy_id, "version": version},
            )
        self._prepare_run_data(run)
        return run

    def _prepare_run_data(self, run):
        conid, binding = run["conid"], run["binding"]
        existing_data = conid in self.data
        if self._fx_run(run):
            self._fx_prepare_data(
                conid,
                binding["execution_plan"]["signal_source"],
                binding["execution_plan"]["policy"],
            )
        else:
            self.subscribe(conid)
        if premarket(run):
            self._premarket_queue(conid)
        if self._stock_run(run) and existing_data:
            self._queue_history(conid, extend=True)

    def arm_preview(
        self, ids, profile_id="smoke", profile_version=None, unattended=False, session_date=None
    ):
        if self._flexible_selection(ids, session_date):
            return self._flexible_preview(
                ids, profile_id, profile_version, unattended, session_date
            )
        # Interest only: polling never sends a credit request. The paced background
        # coordinator decides whether this review needs new evidence.
        interest = getattr(self, "_credit_review_interest", {})
        clock = time.monotonic()
        self._credit_review_interest = {k: v for k, v in interest.items() if clock - v < 6}
        self._credit_review_interest.update({key: clock for key in ids[:5]})
        self._credit_review_interest = dict(list(self._credit_review_interest.items())[-20:])
        if any(self._fx_run(self.store.get("run", key)) for key in ids):
            return self._fx_arm_preview(ids, profile_id, profile_version, unattended)
        if not isinstance(ids, list) or not 1 <= len(ids) <= 5 or len(set(ids)) != len(ids):
            raise ValueError("Select one to five distinct runs.")
        selected_runs = [self.store.get("run", key) for key in ids]
        if any(run is None for run in selected_runs):
            raise ValueError("A selected run no longer exists.")
        if any(run.get("archived") for run in selected_runs):
            raise Conflict(
                "Archived runs cannot be armed. Prepare a new run from the published strategy."
            )
        self.refresh_incidents()
        checks = self.readiness(selected_runs)
        current_profiles = profiles(self.store, simulation=self.environment.crypto)
        stock_only = all(self._stock_run(r) for r in selected_runs)
        if stock_only:
            from .stock_profiles import stock_profiles

            current_profiles = stock_profiles(self.store)
            modern = all(
                (r.get("binding") or {}).get("execution_plan", {}).get("risk_policy")
                == "paper_stock_v2"
                for r in selected_runs
            )
            if modern and profile_id in {"smoke", "qualified", "stock_smoke", "stock_qualified"}:
                profile_id, profile_version = "stock_selected", 2
            if profile_id in {"smoke", "qualified"}:
                profile_id = "stock_" + profile_id
                profile_version = 1
        elif profile_id.startswith("stock_"):
            raise Conflict("Stock profiles require separately reviewed schema-7 stock runs.")
        if profile_version is None:
            profile_version = max(
                (p["version"] for p in current_profiles if p["id"] == profile_id), default=1
            )
        profile = self.store.get("risk_profile", f"{profile_id}:{profile_version}")
        if not profile:
            raise ValueError("Select a published risk profile.")
        if stock_only and any(
            (
                (r.get("binding") or {}).get("execution_plan", {}).get("risk_policy")
                == "paper_stock_v2"
            )
            != (profile.get("risk_policy") == "paper_stock_v2")
            for r in selected_runs
        ):
            raise Conflict("Review runs using different risk-policy generations separately.")
        if ("stock_units" in profile) != stock_only:
            raise Conflict(
                "Select a stock risk profile for schema-7 runs, "
                "or a legacy profile for legacy runs."
            )
        if "daily_loss" in profile:
            raise Conflict(
                "This historical profile contains a retired daily-loss limit. "
                "Select its replacement version."
            )
        if self.environment.crypto:
            checks.append(
                check(
                    "verified_build",
                    "Verified application build",
                    self.code_verified,
                    "Run the verification gate for this build.",
                )
            )
            if unattended:
                raise Conflict("Crypto simulation currently requires a supervised session.")
        else:
            crypto_only = all(
                (self.store.get("run", key) or {}).get("execution") == "crypto_breakout"
                for key in ids
            )
            if crypto_only or stock_only:
                checks.append(
                    check(
                        "verified_build",
                        "Verified application build",
                        self.code_verified,
                        "Run the verification gate for this build.",
                    )
                )
            else:
                checks.extend(
                    qualification_checks(self.store, profile, unattended, self.code_verified)
                )
        selected = []
        selected_policies = {
            (self.store.get("run", key) or {}).get(
                "session_policy", self.environment.session_policy
            )
            for key in ids
        }
        if len(selected_policies) != 1:
            raise Conflict("Review runs with different session policies separately.")
        policy = next(iter(selected_policies))
        bounds = None if stock_only else session_bounds(datetime.now(UTC), policy)
        if stock_only:
            schedules = [self._stock_session(r) for r in selected_runs]
            intervals = [s.bounds(datetime.now(UTC)) for s in schedules]
            bounds = (
                (max(b[0] for b in intervals), min(b[1] for b in intervals))
                if all(intervals)
                else None
            )
        window = bool(bounds and bounds[0] <= datetime.now(UTC) < bounds[1] - timedelta(minutes=15))
        if stock_only:
            window = window and all(s.tradable(datetime.now(UTC)) for s in schedules)
        checks.append(
            check(
                "session",
                "UTC crypto session"
                if policy == "utc_24x7"
                else "Approved pre-market + regular session"
                if any(premarket(r) for r in selected_runs)
                else "Regular trading session",
                window,
                "Arm before the last 15 minutes of the UTC day."
                if policy == "utc_24x7"
                else "Arm during the exchange session, before the last 15 minutes.",
                "/desk",
            )
        )
        reserved_runs = {r["run_id"] for r in self.store.list("reservation") if r.get("active")}
        active = [
            r
            for r in self.store.list("run")
            if r["id"] not in ids
            and (
                r.get("armed")
                or r.get("authorization_status") == "temporarily_suspended"
                or r["id"] in reserved_runs
            )
        ]
        for key in ids:
            run = self.store.get("run", key)
            if not run:
                raise ValueError("A selected run no longer exists.")
            selected.append(run)
            checks.append(
                check(
                    "binding_" + key,
                    "Approved contract identity",
                    self._binding_valid(run),
                    "The resolved contract must match the immutable run binding.",
                )
            )
            if not self.environment.crypto:
                document = self.store.version(run["strategy_id"], run["version"])["document"]
                reason = (
                    run.get("capability_error")
                    if self._stock_run(run)
                    else execution_reason(self.contracts.get(run["conid"], {}), document)
                )
                checks.append(
                    check(
                        "capability_" + key,
                        "Contract execution capability",
                        reason is None,
                        reason or "Supported IBKR paper adapter.",
                    )
                )
            if run.get("execution") == "crypto_breakout":
                checks.append(
                    check(
                        "crypto_supervised_" + key,
                        "Supervised local protection",
                        not unattended,
                        (
                            "Local crypto stops require this application, a verified "
                            "connection and fresh trades."
                        ),
                    )
                )
            health = self._run_feed_health(run)
            checks.append(
                {
                    **check(
                        "data_" + key,
                        f"{run['symbol']} data and warm-up",
                        health["execution_fresh"],
                        health["execution_detail"],
                        None,
                    ),
                    "status": health.get(
                        "status", "ready" if health["execution_fresh"] else "waiting"
                    ),
                }
            )
            if (
                not self.environment.crypto
                and not self._stock_run(run)
                and execution_reason(
                    self.contracts.get(run["conid"], {}),
                    self.store.version(run["strategy_id"], run["version"])["document"],
                )
            ):
                continue
            evaluated = (
                self._runtime(run).get("last_result", {}) if self._run_history_ready(run) else {}
            )
            checks.append(
                check(
                    "indicators_" + key,
                    f"{run['symbol']} strategy inputs ready",
                    bool(self._runtime(run)["market"].closed)
                    if self._paired_run(run)
                    or run.get("execution") in {"crypto_breakout", "stock_breakout"}
                    else evaluated.get("entry") is not None and evaluated.get("stop") is not None,
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
            if self._stock_run(run):
                checks.append(
                    check(
                        "stock_rollout",
                        "Stock arming enabled",
                        os.environ.get("OMS_DISABLE_STOCK_ARM") != "1",
                        "New schema-7 arming is disabled by the execution host rollback setting.",
                    )
                )
                checks.extend(self._stock_checks(run, profile))
                checks.append(
                    check(
                        "stock_supervised_" + key,
                        "Supervised stock qualification",
                        not unattended,
                        "Stock qualification currently requires supervised operation.",
                    )
                )
            if self._paired_run(run):
                checks.append(
                    check(
                        "oca_supervised_" + key,
                        "Supervised paired entries",
                        not unattended,
                        "OCA entries currently require supervised operation.",
                    )
                )
                checks.append(
                    check(
                        "oca_clear_" + key,
                        "Prior OCA group reconciled",
                        all(g["state"] in {"cancelled", "complete"} for g in self._oca_groups(key)),
                        "Wait for both parents, protective children and fills to reconcile.",
                    )
                )
                if not self.environment.crypto:
                    checks.append(
                        check(
                            "oca_borrow_" + key,
                            "Shortable shares available",
                            self._oca_borrow_ready(run["conid"], Decimal(1)),
                            "Fresh borrow data is required. A broker credit preview follows "
                            "arming.",
                        )
                    )
                    checks.append(
                        check(
                            "oca_qualification_" + key,
                            "OCA paper qualification",
                            self._stock_run(run)
                            or profile["shares"] == 1
                            or self._oca_can_expand(),
                            "Use one legal lot until both directions qualify for this contract."
                            if self._stock_run(run)
                            else "Use one share until long and short paper OCA cycles qualify.",
                        )
                    )
        symbols = [r["conid"] for r in active + selected]
        shared_stock_only = all(
            self._stock_run(r) for r in active + selected if symbols.count(r["conid"]) > 1
        )
        checks.append(
            check(
                "distinct_symbols",
                "Distinct contracts and capacity",
                shared_stock_only and len(symbols) <= 5,
                "At most five runs. Stock runs can share data; entry and position capacity "
                "on the same contract is serialized. Legacy runs require distinct contracts.",
                "/desk",
            )
        )
        checks.append(
            check(
                "profile_capacity",
                "Selected risk-profile capacity",
                len(active + selected) <= profile["runs"],
                f"This profile allows {profile['runs']} runs and up to "
                + (
                    (
                        "the selected legal quantity; optional published ceilings apply."
                        if profile.get("risk_policy") == "paper_stock_v2"
                        else "one minimum legal lot; published financial caps apply."
                    )
                    if stock_only
                    else f"{profile.get('quantity', profile.get('shares'))} units per run."
                ),
                "/settings",
            )
        )
        restrictions = self.incidents.applicable(selected)
        for item in checks:
            if not item["passed"] and (
                item["code"] == "session" or item["code"].startswith("indicators_")
            ):
                item.update(status="waiting", remediation=None)
        review_fingerprint = digest(
            {
                "instance": self.process_identity,
                "context": getattr(self, "paper_context_token", None),
                "runs": [
                    {
                        "id": r["id"],
                        "version": r["version"],
                        "binding": (r.get("binding") or {}).get("hash"),
                        "entries": r.get("entries", 0),
                    }
                    for r in selected
                ],
                "profile": profile,
                "unattended": unattended,
                "recoveries": [{"id": i["id"], "revision": i["revision"]} for i in restrictions],
                "resume_policy": RESUME_POLICY
                if profile.get("risk_policy") == "paper_stock_v2"
                else None,
            }
        )
        return {
            "review_fingerprint": review_fingerprint,
            "policy_replacement": self.policy_replacement_preview(selected),
            "resume_policy": RESUME_POLICY
            if profile.get("risk_policy") == "paper_stock_v2"
            else None,
            "eligible": all(c["passed"] for c in checks),
            "can_authorize": all(c["passed"] for c in checks),
            "can_dispatch": all(c["passed"] for c in checks),
            "eligible_after_recovery_ack": all(
                c["passed"] for c in checks if c["code"] != "incidents"
            )
            and 0 < len(restrictions) <= 200
            and all(i["restriction"] == "ready_for_release" for i in restrictions),
            "recoveries": self.incident_recoveries(selected),
            "review_instance": self.process_identity,
            "checks": checks,
            "runs": selected,
            "expires_at": bounds[1].isoformat() if bounds else None,
            "entry_cutoff": (bounds[1] - timedelta(minutes=15)).isoformat() if bounds else None,
            "limits": profile,
            "crypto_entries": [
                {
                    "run_id": run["id"],
                    "cash_ceiling": str(self._crypto_ceiling(run, profile)),
                    "protection_type": "locally_monitored",
                    "stop_percent": "1",
                }
                for run in selected
                if run.get("execution") == "crypto_breakout"
            ],
            "paired_entries": [
                self._oca_preview(run, profile)
                for run in selected
                if self._paired_run(run)
                and (self.environment.crypto or not run.get("capability_error"))
            ],
            "summaries": [
                {"run_id": run["id"], **self.store.version(run["strategy_id"], run["version"])}
                for run in selected
            ],
            "environment": self.environment.name,
            "session_policy": policy,
            "authorization": "supervised_simulation_session"
            if self.environment.crypto
            else "unattended_paper_session"
            if unattended
            else "supervised_paper_session",
        }

    def arm(
        self,
        ids,
        mutation_id,
        profile_id="smoke",
        profile_version=None,
        unattended=False,
        recovery_acknowledgments=None,
        review_instance=None,
        actor="local-operator",
        local_protection_acknowledged=False,
        execution_plan_revisions=None,
        review_fingerprint=None,
        resume_policy=None,
        fx_policy_revision=None,
        funding_policy_acknowledged=None,
        session_date=None,
    ):
        acknowledgments = recovery_acknowledgments or []
        revisions = execution_plan_revisions or {}
        prior = self.store.get("mutation", mutation_id)
        if prior:
            if (
                prior.get("fx_policy_revision") != fx_policy_revision
                or prior.get("funding_policy_acknowledged") != funding_policy_acknowledged
                or prior.get("review_fingerprint") != review_fingerprint
                or prior.get("resume_policy") != resume_policy
                or prior["ids"] != ids
                or prior.get("profile_id", "smoke") != profile_id
                or prior.get("profile_version", 1) != profile_version
                or prior.get("unattended", False) != unattended
                or prior.get("recovery_acknowledgments", []) != acknowledgments
                or prior.get("actor", "local-operator") != actor
                or prior.get("execution_plan_revisions", {}) != revisions
                or prior.get("local_protection_acknowledged", False)
                != local_protection_acknowledged
                or prior.get("requested_session_date") != session_date
            ):
                raise Conflict("This action identifier was already used for a different selection.")
            return prior["result"]
        preview = self.arm_preview(ids, profile_id, profile_version, unattended, session_date)
        modern = preview["limits"].get("risk_policy") == "paper_stock_v2"
        if (modern or review_fingerprint is not None) and review_fingerprint != preview[
            "review_fingerprint"
        ]:
            raise Conflict("Reviewed decisions changed. Refresh the authorization review.")
        if modern and (resume_policy != RESUME_POLICY or review_instance != self.process_identity):
            raise Conflict(
                "Review the current paper policy and routine resumption terms before arming."
            )
        if modern and os.environ.get("OMS_DISABLE_MINIMAL_PAPER_ARM") == "1":
            raise Conflict("New paper-policy arming is disabled by the rollback setting.")
        if not modern and resume_policy is not None:
            raise Conflict("This binding does not support automatic entry resumption.")
        for selected in preview["runs"]:
            funding_policy = ((selected.get("binding") or {}).get("execution_plan") or {}).get(
                "funding_policy"
            )
            acknowledged = (
                funding_policy_acknowledged
                if isinstance(funding_policy_acknowledged, list)
                else [funding_policy_acknowledged]
            )
            if funding_policy and funding_policy not in acknowledged:
                raise Conflict("Review broker-permitted borrowing and funding terms before arming.")
            if (
                funding_policy == "paper_buying_power_v1"
                and os.environ.get("OMS_DISABLE_PAPER_BUYING_POWER_ARM") == "1"
            ):
                raise Conflict("New paper buying-power authorization is disabled by rollback.")
            if self._fx_run(selected) and selected["binding"]["execution_plan"]["policy"] not in (
                fx_policy_revision if isinstance(fx_policy_revision, list) else [fx_policy_revision]
            ):
                raise Conflict(
                    "Review the FX signal, entry, protection and funded-currency policy "
                    "terms before arming."
                )
            if self._stock_run(selected) or self._fx_run(selected):
                if revisions.get(selected["id"]) != selected["binding"]["execution_plan"]["hash"]:
                    raise Conflict("The stock execution plan must be reviewed again.")
                if (
                    selected["protection_type"] == "locally_monitored"
                    and not local_protection_acknowledged
                ):
                    raise Conflict(
                        "Explicitly acknowledge locally monitored protection before arming."
                    )
        if not preview["eligible"] and not (
            acknowledgments and preview["eligible_after_recovery_ack"]
        ):
            raise Conflict(
                "The selected runs are blocked. Resolve the readiness checks and review again."
            )
        with self.store.transaction() as db:
            owner = self.store.read(db, "workspace", "engine_owner") or {}
            if owner.get("instance") != self.process_identity or owner.get("state") == "stopped":
                raise Conflict("Engine ownership changed. Refresh the review.")
            if review_instance is not None and review_instance != self.process_identity:
                raise Conflict("Engine changed. Refresh the review.")
            if acknowledgments:
                episodes = self.validate_recovery_acknowledgments(
                    db,
                    acknowledgments,
                    preview["runs"],
                    review_instance,
                )
                for episode in episodes:
                    self.incidents.release_in(
                        db,
                        episode["id"],
                        episode["revision"],
                        actor,
                        "Explicit recovery acknowledgment during arming.",
                        evidence=episode["release_evidence"],
                    )
            elif self.incidents.applicable(preview["runs"], db):
                raise Conflict("Applicable incident restrictions require fresh recovery review.")
            for run in preview["runs"]:
                if (self.store.read(db, "safety", "emergency") or {}).get("active"):
                    raise Conflict("Emergency stop became active. Review the session again.")
                run.update(
                    armed=True,
                    state="waiting_session" if run.get("valid_from", "") > now() else "armed",
                    authorization_status="authorized",
                    authorization_instance=self.process_identity,
                    authorization_context=getattr(self, "paper_context_token", None),
                    resume_policy=resume_policy,
                    fx_policy_revision=run["binding"]["execution_plan"]["policy"]
                    if self._fx_run(run)
                    else None,
                    funding_policy_acknowledged=funding_policy_acknowledged,
                    funding_currency=getattr(self, "account_base_currency", None)
                    if self._fx_run(run)
                    else run.get("funding_currency"),
                    live_after=now(),
                    expires_at=run.get("expires_at")
                    if preview.get("flexible_session")
                    else preview["expires_at"],
                    authorized_at=now(),
                    authorization_id=mutation_id,
                    epoch=self.broker.epoch,
                    blocking_reason=None,
                    limits=preview["limits"],
                    unattended=unattended,
                    entries=run.get("entries", 0)
                    if not (
                        self._paired_run(run)
                        or run.get("execution")
                        in {"crypto_breakout", "stock_breakout", "fx_breakout"}
                    )
                    and run.get("session_date") == datetime.now(UTC).date().isoformat()
                    else 0,
                    session_date=preview.get("session_date", datetime.now(UTC).date().isoformat()),
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
                        "review_fingerprint": review_fingerprint,
                        "resume_policy": resume_policy,
                        "fx_policy_revision": fx_policy_revision,
                        "funding_policy_acknowledged": funding_policy_acknowledged,
                        "funding_currency": run.get("funding_currency"),
                        "limits": preview["limits"],
                        "recovery_acknowledgments": acknowledgments,
                        "actor": actor,
                        "local_protection_acknowledged": local_protection_acknowledged,
                        "execution_plan_revisions": revisions,
                        "binding": run.get("binding"),
                        "strategy_hash": self.store.version(run["strategy_id"], run["version"])[
                            "hash"
                        ],
                        "session_policy": run.get(
                            "session_policy", self.environment.session_policy
                        ),
                    },
                )
            self.store.write(
                db,
                "mutation",
                mutation_id,
                {
                    "ids": ids,
                    "review_fingerprint": review_fingerprint,
                    "resume_policy": resume_policy,
                    "fx_policy_revision": fx_policy_revision,
                    "funding_policy_acknowledged": funding_policy_acknowledged,
                    "profile_id": profile_id,
                    "profile_version": profile_version,
                    "unattended": unattended,
                    "recovery_acknowledgments": acknowledgments,
                    "actor": actor,
                    "local_protection_acknowledged": local_protection_acknowledged,
                    "execution_plan_revisions": revisions,
                    "requested_session_date": session_date,
                    "result": {"armed": ids},
                },
            )
        for run in preview["runs"]:
            self._runtime(run)
        return {"armed": ids}

    def disarm(self, key, reason="Disarmed by operator.", cancellation_reason="run_disarmed"):
        run = self.store.get("run", key)
        if not run:
            raise ValueError("Run not found.")
        run.update(
            armed=False,
            authorization_status="expired"
            if "expired" in reason.lower()
            else "completed"
            if "Trade completed" in reason
            or "no fill" in reason.lower()
            or "zero-fill" in reason.lower()
            else "revoked",
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
                self.cancel_entry(order["id"], reason=cancellation_reason)
        return run

    def emergency(self, active):
        self.store.set_emergency(active)
        if active:
            for run in self.store.list("run"):
                self.disarm(
                    run["id"], "Emergency stop is active.", cancellation_reason="emergency_stop"
                )
        return {"active": active}

    def cancel_entry(self, key, reason="operator"):
        from .order_status import CANCEL_REASONS

        if reason not in CANCEL_REASONS:
            raise ValueError("Unknown entry cancellation reason.")
        order = next((o for o in self.store.orders() if o["id"] == key), None)
        if not order or order["payload"].get("purpose", "entry") != "entry":
            raise ValueError("Select a known entry order.")
        if is_pair(order["payload"]):
            self._oca_cancel(order, "operator_or_disarm")
            return {"state": "cancel_pending"}
        if order["state"] in {"cancel_pending", "cancelled", "filled", "rejected"}:
            return {"state": order["state"]}
        self.store.transition(
            key, "cancel_pending", {"action": "cancel_requested", "reason": reason}
        )
        self.invalidate_reconciliation()
        self.next_reconcile = time.monotonic() + 1
        self._queue_cancel(order["broker_id"], "entry", reason=reason)
        return {"state": "cancel_pending"}

    def _runtime(self, run, reset=False):
        if self._fx_run(run):
            return self._fx_runtime(run, reset)
        if run["id"] not in self.runtime or reset:
            graph = bind_graph(
                self.store.version(run["strategy_id"], run["version"])["document"],
                run.get("binding"),
            )
            market = (
                StockMarket(graph, self._stock_session(run))
                if self._stock_run(run)
                else Market(graph)
            )
            bars = self.history_bars.get(run["conid"], {60: {}, 5: {}})
            if premarket(run):
                bars = (
                    getattr(self, "premarket_history", {})
                    .get(run["conid"], {})
                    .get("bars", {60: {}, 5: {}})
                )
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
                "oca_live_since": now(),
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

    def _binding_valid(self, run):
        if self._fx_run(run):
            return self._fx_binding_valid(run)
        from .stock_fees import AUTO_REFERENCE

        binding = run.get("binding")
        if not binding:
            return True
        published = self.store.version(run["strategy_id"], run["version"])
        current = self.contracts.get(run["conid"], {})
        pinned_rules = binding["contract"].get("stock_rules") or {}
        if (
            pinned_rules
            and pinned_rules.get("reference") != AUTO_REFERENCE
            and (current.get("stock_rules") or {}).get("reference") == AUTO_REFERENCE
        ):
            # Preparing an automatic-policy run must not reinterpret an older
            # binding. Explicit legacy rule amendments still invalidate it.
            current = {
                **current,
                "stock_rules": self.store.get("stock_rules", str(run["conid"])) or pinned_rules,
            }
        fields = (
            "conid",
            "symbol",
            "sec_type",
            "currency",
            "routing_exchange",
            "primary_exchange",
            "local_symbol",
            "expiry",
            "strike",
            "right",
            "multiplier",
        )
        return (
            binding["hash"] == digest({k: v for k, v in binding.items() if k != "hash"})
            and binding["strategy_hash"] == published["hash"]
            and all(binding["contract"].get(k) == current.get(k) for k in fields)
            and (
                not self._stock_run(run)
                or all(
                    binding["contract"].get(k) == current.get(k)
                    for k in (
                        "stock_rules",
                        "market_rule",
                        "order_types",
                        "time_zone",
                        "price_magnifier",
                    )
                    if not (premarket(run) and k == "liquid_hours")
                )
            )
        )

    def _tick(self, event):
        conid = event["conid"]
        if conid not in self.data:
            return
        stamp = datetime.fromtimestamp(event["timestamp"], UTC)
        capture = event.get("capture") or self.store.capture({"source": "ibkr_last", **event})
        previous = self.data[conid].get("last_valid_trade_at")
        try:
            if number(event["price"]) <= 0 or number(event["size"]) < 0:
                raise GraphError("Invalid trade price or volume.")
            if previous is not None and stamp < datetime.fromisoformat(previous):
                raise GraphError("Out-of-order trade observation.")
        except GraphError:
            self._data_gap(conid, "Late or invalid observations require candle repair.")
            return
        self.data[conid].update(
            price=event["price"],
            received_at=event.get("received_at", now()),
            source_at=stamp.isoformat(),
            sequence=event.get("sequence"),
        )
        buffer = self.buffered_ticks.setdefault(conid, deque(maxlen=200000))
        if (
            not self.data[conid].get("warm")
            and len(buffer) == buffer.maxlen
            and any(
                self._requires_downloaded_history(r)
                for r in self._data_dependencies()["runs"] + self.active_preparations()
                if r.get("conid") == conid
            )
        ):
            self.incident(
                "warmup_overflow",
                "The warm-up tick buffer filled. Reduce subscriptions and repair history.",
                conid=conid,
            )
            return
        buffer.append(event)
        if abs((datetime.now(UTC) - stamp).total_seconds()) > 15:
            if self.data[conid].get("warm"):
                self._data_gap(conid, "Trade timestamps are stale or ahead of the clock.")
            return
        runs = getattr(self, "_batch_runs", None) or self.store.list("run")
        for run in runs:
            market = self.runtime.get(run["id"], {}).get("market")
            if (
                run["conid"] == conid
                and market
                and market.closed_until
                and stamp < market.closed_until
            ):
                self._data_gap(
                    conid, "A late trade belongs to a completed candle; repair continuity."
                )
                return
        self.data[conid]["last_valid_trade_at"] = stamp.isoformat()
        self.feed_observed(event)
        self._crypto_trade(event)
        self._stock_trade(event)
        for run in runs:
            if not self._run_history_ready(run):
                continue
            if run.get("archived") or run.get("diagnostic_test"):
                continue
            if run["conid"] != conid or (
                not self.environment.crypto and run.get("capability_error")
            ):
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
        if self._stock_run(run) and not state["market"].tradable(datetime.now(UTC)):
            return
        if run.get("execution") == "stock_breakout":
            self._stock_candidate(self.store.get("run", run["id"]), state, context, capture)
            return
        if run.get("execution") == "crypto_breakout":
            self._crypto_candidate(self.store.get("run", run["id"]), state, context, capture)
            return
        if self._paired_run(run):
            self._oca_candidate(self.store.get("run", run["id"]), state, context, capture)
            return
        seeded = state["seeded"]
        result, signal = evaluate_step(state, context)
        if not seeded:
            return  # Warm-up never creates retrospective entries.
        position = self.owned().get(run["id"])
        if position and position["quantity"] != 0:
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
            self._signal_detect(
                run,
                {
                    "candle": str(context["bar_start"]),
                    "triggered_at": now(),
                    "expires_at": (datetime.now(UTC) + timedelta(seconds=15)).isoformat(),
                },
                capture,
            )
            try:
                self._enter(run, result, context, capture)
            except (ValueError, Conflict) as exc:
                from .credit import CreditPending

                self._signal_outcome(
                    run, "checking" if isinstance(exc, CreditPending) else "blocked", str(exc)
                )
                run["blocking_reason"] = str(exc)
                self.store.put("run", run["id"], run)
                self.store.event("risk.blocked", {"run_id": run["id"], "reason": str(exc)})

    def _request_exit(self, key):
        if not self.store.get("exit_request", key):
            self.store.put("exit_request", key, {"requested_at": now()})
            self.store.event("exit.requested", {"run_id": key})
        try:
            self.close_position(key, automatic=True)
        except Conflict:
            pass  # The durable request remains pending; broker protection is retained.

    def _clock_evaluations(self):
        stamp = datetime.now(UTC)
        for run in self.store.list("run"):
            if self._fx_run(run):
                continue
            if not run.get("armed") and self.owned().get(run["id"], {}).get("quantity", 0) == 0:
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
                if self._run_history_ready(run) and data.get("live")
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
            bounds = (
                self._run_bounds(run, stamp)
                if run.get("valid_from")
                else state["market"].session_bounds(stamp)
            )
            if (
                bounds
                and bounds[0] <= stamp
                and stamp
                >= bounds[1]
                - timedelta(minutes=state["graph"].document["settings"]["exit_before_close"])
            ):
                position = self.owned().get(run["id"])
                if position and position["quantity"] != 0:
                    self._request_exit(run["id"])
            elif self.store.get("exit_request", run["id"]) or (
                (self.environment.crypto or run.get("execution") == "crypto_breakout")
                and run.get("expires_at", "z") <= stamp.isoformat()
            ):
                position = self.owned().get(run["id"])
                if position and position["quantity"] != 0:
                    self._request_exit(run["id"])

    def _enter(self, run, result, context, capture):
        if not self._session_permission(run):
            raise Conflict("The selected execution session is not open for new entries.")
        if not self._binding_valid(run):
            raise Conflict("Contract identity changed. Prepare and approve a new run binding.")
        if not all(c["passed"] for c in self.readiness([run])) or not (
            self.connection_diagnostics(run["conid"])["eligible"]
            if run.get("diagnostic_test")
            else self._run_feed_health(run)["execution_fresh"]
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
        if premarket(run):
            from .oca import protection_price, rounded

            limit = rounded(limit, increments, True)
            result = {**result, "stop": protection_price(limit, "long", increments)}
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
        stock_reservation = None
        if self._stock_run(run):
            quantity, stock_reservation = self._stock_size(run, [(limit, stop)], profile)
        else:
            quantity = size_entry(
                settings,
                profile,
                limit,
                protective_limit,
                number(self.facts["AvailableFunds"]) - reserved_funds,
                contract,
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
        # Position marks remain mandatory independently of informational account P/L.
        for position in (
            []
            if (run.get("binding") or {}).get("execution_plan", {}).get("risk_policy")
            == "paper_stock_v2"
            else self.owned().values()
        ):
            data = self.data.get(position["conid"], {})
            if position["quantity"] and (
                not data.get("price")
                or not data.get("received_at")
                or (datetime.now(UTC) - datetime.fromisoformat(data["received_at"])).total_seconds()
                > 15
            ):
                raise Conflict("Current position marks are unavailable.")
        key = uuid.uuid4().hex
        payload = {
            "purpose": "entry",
            "outside_rth": extended,
            "stop_limit": str(protective_limit) if extended else None,
            "conid": run["conid"],
            "symbol": run["symbol"],
            "quantity": str(quantity)
            if self.environment.crypto or self._stock_run(run)
            else quantity,
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
        if self._stock_run(run):
            payload.update(self._stock_payload(run, stock_reservation))
            if stock_reservation.get("credit_order_deadline"):
                payload["expires_at"] = stock_reservation["credit_order_deadline"]
            payload.update(
                protection_type=run["protection_type"],
                price_rules=increments,
                execution=run["execution"],
            )
            if run["execution"] == "stock_breakout":
                payload["entry_type"] = "MKT"
            if premarket(run):
                self._premarket_entry(run, payload)
        reserved = self.store.reserve_order(
            key,
            payload,
            run["id"],
            self.next_id,
            stock_reservation
            or {
                "symbol": run["symbol"],
                "risk": str(quantity * (limit - protective_limit)),
                "notional": str(quantity * limit),
            },
        )
        if not self.guard_entry_dispatch(key):
            return
        if premarket(run):
            self.store.put(
                "stock_protection",
                run["id"],
                {
                    "run_id": run["id"],
                    "entry_id": key,
                    "stop": payload["stop"],
                    "quantity": "0",
                    "type": "locally_monitored",
                    "state": "awaiting_fill",
                    "currency": payload["currency"],
                    "price_scale": payload["price_scale"],
                    "average": payload["limit"],
                    "target": None,
                },
            )
            self.store.event(
                "stock.protection.planned",
                {"run_id": run["id"], "entry_id": key, "stop": payload["stop"]},
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
        # A submission failure can revoke authorization inside incident handling.
        # Never overwrite that decision with the pre-dispatch run snapshot.
        run = self.store.get("run", run["id"])
        run.update(entries=run["entries"] + 1, last_signal=now())
        if run.get("armed"):
            run.update(state="entry_working", blocking_reason=None)
        self.store.put("run", run["id"], run)
        self._signal_outcome(
            run,
            "submitted" if run.get("armed") else "uncertain",
            "Paper entry submitted; waiting for broker outcome."
            if run.get("armed")
            else "Submission interrupted; reconciling the existing order.",
            order_id=key,
        )
        self.invalidate_reconciliation()
        self.next_reconcile = time.monotonic() + 2

    def close_position(self, key, automatic=False):
        fx_run = self.store.get("run", key)
        if self._fx_run(fx_run):
            return self._fx_request_exit(
                fx_run,
                "Operator requested FX exit." if not automatic else "Strategy requested FX exit.",
            )
        if (self.store.get("run", key) or {}).get("execution") == "crypto_breakout":
            return self._crypto_close(key)
        position = self.owned().get(key)
        entry = next(
            (o for o in self.store.orders() if position and o["id"] == position["entry_id"]), None
        )
        paired = entry is not None and is_pair(entry["payload"])
        if (
            not position
            or position["quantity"] == 0
            or (
                not self.environment.crypto
                and not (entry and entry["payload"].get("stock_plan"))
                and not paired
                and position["quantity"] != position["quantity"].to_integral_value()
            )
        ):
            raise Conflict("A reconciled owned whole-share position is required.")
        stock_exit = bool(entry and entry["payload"].get("stock_plan"))
        ready = (
            self.position_agreement
            and not self._identity_issues()
            and not self._fill_agreement_issues()
            if stock_exit
            else self.reconciled
        )
        if not ready or not self.attested or time.monotonic() - self.reconciled_at >= 30:
            raise Conflict("Reconcile the paper account before closing an owned position.")
        if not self.store.get("exit_request", key):
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
                    "The broker session is closed. Exit remains pending; protection is retained."
                )
        if any(
            o["run_id"] == key
            and o["payload"].get("purpose") == "exit"
            and o["state"] not in {"cancelled", "rejected", "filled"}
            for o in self.store.orders()
        ):
            return {"state": "exit_pending"}
        quote = self.quotes.get(position["conid"], {}).get(
            "bid" if position["quantity"] > 0 else "ask"
        )
        if (
            not quote
            or (datetime.now(UTC) - datetime.fromisoformat(quote["received_at"])).total_seconds()
            > 15
        ):
            raise Conflict("A current bid is required; protective orders remain in place.")
        identity = uuid.uuid4().hex
        payload = {
            "purpose": "exit",
            "outside_rth": bool(entry and entry["payload"].get("outside_rth")),
            "entry_id": position["entry_id"],
            "conid": position["conid"],
            "symbol": position["symbol"],
            "quantity": str(abs(position["quantity"]))
            if self.environment.crypto or paired or (entry and entry["payload"].get("stock_plan"))
            else int(abs(position["quantity"])),
            "limit": quote["price"],
            "quote_capture": self.store.capture(
                {"source": "exit_quote", "conid": position["conid"], "quote": quote}
            ),
        }
        if entry and entry["payload"].get("stock_plan"):
            payload["stock_plan"] = entry["payload"]["stock_plan"]
            payload["currency"] = payload["stock_plan"]["currency"]
            payload["price_scale"] = payload["stock_plan"]["rules"]["price_scale"]
            if self.store.get("run", key)["protection_type"] == "locally_monitored":
                payload.update(exit_type="MKT", protection_type="locally_monitored")
                if any(
                    o["run_id"] == key and o["state"] not in {"filled", "cancelled", "rejected"}
                    for o in self.store.orders()
                ):
                    return {"state": "exit_pending"}
                run = self.store.get("run", key)
                if premarket(run):
                    previous_exits = [
                        o
                        for o in self.store.orders()
                        if o["run_id"] == key and o["payload"].get("purpose") == "exit"
                    ]
                    rejected = {
                        o["id"]
                        for o in previous_exits
                        if o["state"] == "rejected"
                        or (self.store.get("broker_order", str(o["broker_id"])) or {}).get(
                            "rejection_code"
                        )
                    }
                    request = self.store.get("exit_request", key)
                    if rejected - set(request.get("reviewed_rejections", [])):
                        if (
                            automatic
                            or not self.reconciled
                            or any(
                                i["code"]
                                in {
                                    "order_uncertain",
                                    "order_rejected",
                                    "exit_uncertain",
                                    "dispatch_uncertain",
                                }
                                for i in self.incidents.applicable([run])
                            )
                        ):
                            raise Conflict(
                                "A pre-market exit was rejected. Review broker recovery, "
                                "then explicitly Close the remaining position to retry."
                            )
                        self.store.put(
                            "exit_request",
                            key,
                            {**request, "reviewed_rejections": sorted(rejected)},
                        )
                        self.store.event(
                            "premarket.exit.retry_reviewed",
                            {"run_id": key, "orders": sorted(rejected)},
                        )
                    if previous_exits and not self.reconciled:
                        raise Conflict(
                            "Reconcile the cancelled exit and remaining quantity "
                            "before replacement."
                        )
                    self._premarket_exit_payload(run, payload)
        if paired:
            side = "long" if position["quantity"] > 0 else "short"
            payload.update(
                action="SELL" if side == "long" else "BUY",
                exit_group=entry["payload"]["exit_groups"][side],
                pair_recovery=True,
            )
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
        self.invalidate_reconciliation()
        self.next_reconcile = time.monotonic() + 2
        run = self.store.get("run", key)
        if run:
            run.update(
                state="exiting", blocking_reason="Exit requested; awaiting broker confirmation."
            )
            self.store.put("run", key, run)
        return {"state": "exit_pending"}
