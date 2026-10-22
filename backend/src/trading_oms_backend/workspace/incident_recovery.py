"""Current recovery evidence evaluated by the single execution owner."""

import time
import uuid
from datetime import datetime

from .automatic_recovery import AutomaticRecovery
from .incidents import ROUTINE, SERVICE_RECOVERY, incident_summary
from .store import Conflict


class IncidentRecovery(AutomaticRecovery):
    def _dependency_history_ready(self, conid, regular_only=False):
        if conid in getattr(self, "fx_data", {}):
            required = [
                r
                for r in self._data_dependencies()["runs"] + self.active_preparations(conid)
                if r.get("conid") == conid and self._fx_uses_broker_candles(r)
            ]
            return all(self._fx_feed_health(conid, r)["history_ready"] for r in required)
        from .premarket import premarket

        required = [r for r in self._data_dependencies()["runs"] if r.get("conid") == conid]
        required.extend(self.active_preparations(conid))
        if required and all(not self._requires_downloaded_history(r) for r in required):
            return True
        runs = required
        if not regular_only and runs and all(premarket(r) for r in runs):
            return all(self._run_history_ready(r) for r in runs)
        data = self.data.get(conid, {})
        return bool(data.get("warm") and not data.get("history_failed"))

    def _contained_feed(self, conid, component):
        return any(
            i["scope"] == {"type": "contract", "key": str(conid)}
            and i["code"] in {component + "_feed_failure", "market_data_failure"}
            for i in self.incidents.open()
        )

    def _contain_service_failures(self):
        # Establish narrower holds before the broad service hold can be released.
        if not any(i["code"] in ROUTINE | SERVICE_RECOVERY.keys() for i in self.incidents.open()):
            return
        for conid in self.data:
            for component, state in self.feed_projection(conid).items():
                if state["status"] == "failed" and not self._contained_feed(conid, component):
                    self.incident(
                        component + "_feed_failure",
                        "This contract's feed remains unavailable after service recovery.",
                        conid=conid,
                        diagnostic=state.get("diagnostic"),
                        notify=False,
                    )

    def _recovery_checks(self, item, retired=False):
        checks = []

        def add(code, title, passed, detail):
            checks.append({"code": code, "title": title, "passed": bool(passed), "detail": detail})

        health = self.watchdog_status()
        add("watchdog", "Current watchdog health", health["ready"], health["detail"])
        if item["code"] == "watchdog":
            try:
                timestamp = datetime.fromisoformat(item["last_at"]).timestamp()
            except (ValueError, TypeError):
                timestamp = float("inf")
            add(
                "watchdog_after",
                "Heartbeat after the interruption",
                (health.get("checked_at") or 0) > timestamp,
                "Wait for a fresh watchdog heartbeat after this incident.",
            )
        add(
            "paper_context",
            "Verified paper connection",
            self.connected and self.attested and self.broker.paper_context,
            "Restore and attest the verified paper connection.",
        )
        add(
            "reconciliation",
            "Fresh account and protection reconciliation",
            self.reconciled and time.monotonic() - self.reconciled_at < 30,
            "Complete a fresh successful account and protection reconciliation.",
        )
        proof = self.reconciliation_evidence or {}
        add(
            "reconciliation_after",
            "Reconciliation begun after the latest failure",
            proof.get("instance") == self.process_identity
            and proof.get("epoch") == self.broker.epoch
            and proof.get("started_sequence", -1) >= item["failure_sequence"]
            and proof.get("ready"),
            "A complete reconciliation must begin after the latest incident occurrence.",
        )
        add(
            "overflow",
            "Callback queue healthy",
            not self.broker.overflow.is_set(),
            "Restart and reconcile after the callback overflow.",
        )
        add(
            "clock",
            "Gateway clock synchronized",
            self.clock_ok,
            "Receive a synchronized Gateway clock heartbeat.",
        )
        add(
            "progress",
            "Engine progressing",
            time.monotonic() - self.last_loop < 10,
            "Wait for sustained successful engine progress.",
        )
        if item["scope"]["type"] == "contract" and not retired:
            conid = int(item["scope"]["key"])
            data = self.data.get(conid, {})
            components = self.feed_projection(conid)
            # A component episode tests its own feed. Combined legacy incidents
            # conservatively test every component and established history continuity.
            selected = item["code"].removesuffix("_feed_failure")
            if selected in {"regular_history", "premarket_history"}:
                selected = "history"
            targets = (
                [selected]
                if selected in {"quote", "trade", "history"}
                else ["quote", "trade", "history"]
            )
            for component in targets:
                state = components.get(component)
                passed = (
                    state["status"] == "healthy"
                    if state
                    else bool(
                        data.get("warm") and data.get("live") and not data.get("history_failed")
                    )
                )
                if component == "quote":
                    passed = (
                        passed
                        and data.get("live")
                        and data.get("subscription_status")
                        not in {"failed", "unavailable", "queued", "rejected"}
                    )
                if component == "history":
                    passed = self._dependency_history_ready(
                        conid, item["code"] == "regular_history_feed_failure"
                    )
                    if item["code"] == "premarket_history_feed_failure":
                        passed = self._run_history_ready(
                            {
                                "conid": conid,
                                "binding": {
                                    "execution_plan": {"session_mode": "premarket_regular"}
                                },
                            }
                        )
                diagnostic = (state or {}).get("diagnostic") or {}
                fx = item.get("diagnostic") or {}
                if fx.get("fx"):
                    source = fx.get("signal_source")
                    cache = self._fx_cache(conid)
                    feed = (
                        cache["sources"].get(source, {})
                        if source in {"MIDPOINT", "BID", "ASK"}
                        else cache["feeds"].get(source, {})
                    )
                    passed = (
                        feed.get("epoch") == self.broker.epoch
                        and feed.get("status") in {"healthy", "completed"}
                        and data.get("live")
                    )
                add(
                    "feed_" + component,
                    component.title() + " feed recovered",
                    passed,
                    diagnostic.get("detail")
                    or "Restore this contract's subscription and complete valid history.",
                )
        if item["code"] == "premarket_exit_pending":
            position = self.owned().get(item["scope"]["key"], {})
            add(
                "exit_complete",
                "Remaining position closed and reconciled",
                not position.get("quantity"),
                "Complete or explicitly resolve the outstanding exit in TWS and reconcile.",
            )
        if item["code"] in SERVICE_RECOVERY and item["review_policy"] == "arming":
            code = SERVICE_RECOVERY[item["code"]]
            farm = (item.get("diagnostic") or {}).get("farm")
            proof = getattr(self, "_service_recovery", {}).get((code, farm), {})
            new_context = item.get("instance") != self.process_identity or (
                item.get("connection_epoch") is not None
                and item["connection_epoch"] != self.broker.epoch
            )
            matching = (
                proof.get("epoch") == self.broker.epoch
                and proof.get("sequence", -1) > item["failure_sequence"]
            )
            if not farm:
                matching = any(
                    p.get("epoch") == self.broker.epoch
                    and p.get("sequence", -1) > item["failure_sequence"]
                    for (c, _), p in getattr(self, "_service_recovery", {}).items()
                    if c == code
                )
            add(
                "broker_service",
                "Broker service recovery confirmed",
                new_context or matching,
                f"Wait for IBKR service recovery code {code} after this failure.",
            )
        if item["code"] in ROUTINE | SERVICE_RECOVERY.keys():
            new_context = item.get("instance") != self.process_identity or (
                item.get("connection_epoch") is not None
                and item["connection_epoch"] != self.broker.epoch
            )
            code = SERVICE_RECOVERY.get(item["code"])
            dependencies = self._data_dependencies()
            execution_dependencies = (
                {r["conid"] for r in dependencies["runs"]}
                | dependencies["priority"]
                | set(getattr(self, "_preparation_dependencies", {}))
            )
            required = dependencies["contracts"]
            for conid in required:
                data = self.data.get(conid, {})
                needed = (
                    ("quote", "trade", "history")
                    if new_context or code is None
                    else ("history",)
                    if code == 2106
                    else ("quote", "trade")
                )
                feeds = self.feed_projection(conid)
                healthy = True
                for component in needed:
                    state = feeds.get(component, {})
                    if self._contained_feed(conid, component):
                        continue
                    if component == "history":
                        component_ready = (
                            conid not in execution_dependencies
                            or self._dependency_history_ready(conid)
                        )
                    else:
                        component_ready = (
                            data.get("live")
                            and data.get("subscription_status")
                            not in {"failed", "unavailable", "queued", "rejected"}
                            and state.get("status", "healthy") == "healthy"
                        )
                    healthy = healthy and component_ready
                add(
                    f"service_feed_{conid}",
                    f"Affected subscription {conid} recovered or contained",
                    healthy,
                    "Restore applicable feeds; contract restrictions retain isolated failures.",
                )
        if item["code"] == "callback_overflow":
            add(
                "overflow_restart",
                "Restart after callback overflow",
                item.get("instance") != self.process_identity,
                "Restart the application after callback overflow before recovery review.",
            )
        if item["code"] == "monitoring_unavailable":
            heartbeat = self.store.get("monitoring", "last_heartbeat") or {}
            try:
                age = (
                    time.time() - datetime.fromisoformat(heartbeat.get("timestamp", "")).timestamp()
                )
            except (ValueError, TypeError):
                age = float("inf")
            add(
                "monitoring",
                "Unattended monitoring heartbeat",
                heartbeat.get("passed") and 0 <= age <= 90,
                "Restore the required unattended monitoring heartbeat.",
            )
        return checks

    def _incident_evidence(self, item, retired=False):
        if retired:
            proof = self.reconciliation_evidence or {}
            if not (
                self.reconciled
                and time.monotonic() - self.reconciled_at < 30
                and proof.get("ready")
                and proof.get("instance") == self.process_identity
                and proof.get("epoch") == self.broker.epoch
            ):
                return (
                    None,
                    "Waiting for current completed reconciliation "
                    "before retiring an unused dependency.",
                )
            return {
                "engine_instance": self.process_identity,
                "connection_epoch": self.broker.epoch,
                "reconciliation_id": proof["id"],
                "healthy_seconds": 0,
                "dependency": {"scope": item["scope"], "state": "no_execution_dependency"},
            }, None
        for check in self._recovery_checks(item, retired):
            if not check["passed"]:
                return None, check["detail"]
        health = self.watchdog_status()
        if not health["ready"]:
            return None, health["detail"]
        proof = self.reconciliation_evidence
        return {
            "engine_instance": self.process_identity,
            "connection_epoch": self.broker.epoch,
            "reconciliation_id": proof["id"],
            "reconciliation_started_at": proof["started_at"],
            "reconciliation_completed_at": proof["completed_at"],
            "watchdog_checked_at": health["checked_at"],
            "healthy_seconds": 0,
            **(
                {
                    "dependency": {
                        "scope": item["scope"],
                        "state": "inactive_without_exposure_or_work",
                    }
                }
                if retired
                else {}
            ),
        }, None

    def refresh_incidents(self):
        """Release verified routine restrictions, never authorize a run."""
        clock = time.monotonic()
        self._contain_service_failures()
        active = self.incidents.open()
        active_ids = {item["id"] for item in active}
        self._incident_stability = {
            k: v for k, v in self._incident_stability.items() if k in active_ids
        }
        for item in active:
            with self.store.connect() as db:
                retired = self.automatic_recovery_enabled and self.unused_feed(item, db)
            evidence, detail = self._incident_evidence(item, retired)
            key = (item["failure_sequence"], self.process_identity, self.broker.epoch)
            if evidence:
                self._incident_stability[item["id"]] = (key, clock, clock)
            else:
                self._incident_stability.pop(item["id"], None)
            with self.store.transaction() as db:
                if not self.recovery_owner(db):
                    continue
                latest = self.incidents.get(item["id"], db)
                if latest["revision"] != item["revision"]:
                    self._incident_stability.pop(item["id"], None)
                    continue
                if evidence:
                    # Re-evaluate under ownership/episode lock before releasing.
                    current, why = self._incident_evidence(latest, retired)
                    if not current or (retired and not self.unused_feed(latest, db)):
                        self._incident_stability.pop(item["id"], None)
                        self.incidents.withhold_in(db, latest, why or "Dependency changed.")
                        continue
                    if retired:
                        self.automatic_release(db, latest, current, retired=True)
                    else:
                        corrected = self.corrected_fault_recoverable(latest, db)
                        latest = self.incidents.recover_in(db, latest, current)
                        if self.automatic_recovery_enabled and (
                            self._conclusive_recovery(latest, db)
                        ):
                            if corrected:
                                from .fault_policy import POLICY

                                current["classification_policy"] = POLICY
                            self.automatic_release(db, latest, current, corrected=corrected)
                else:
                    self.incidents.withhold_in(db, latest, detail)

    def _reviewable_incidents(self, runs):
        self.refresh_incidents()
        return self.incidents.applicable(runs)

    def validate_recovery_acknowledgments(self, db, acknowledgments, runs, review_instance):
        if not self.reconciled:
            raise Conflict("Wait for the in-progress reconciliation to complete.")
        if review_instance != self.process_identity:
            raise Conflict("The engine changed. Refresh recovery and arming review.")
        active = {item["id"]: item for item in self.incidents.applicable(runs, db)}
        supplied = {item["id"]: item["revision"] for item in acknowledgments}
        if len(supplied) != len(acknowledgments) or set(supplied) != set(active):
            raise Conflict("Acknowledge exactly the current applicable recovery episodes.")
        for key, item in active.items():
            if item["restriction"] != "ready_for_release" or item["revision"] != supplied[key]:
                raise Conflict(
                    "An incident is active, changed, or requires dedicated recovery review."
                )
            evidence, detail = self._incident_evidence(item)
            stable = self._incident_stability.get(key)
            if not evidence or not stable or time.monotonic() - stable[2] > 10:
                raise Conflict(detail or "Recovery stability expired. Refresh the review.")
            item["release_evidence"] = evidence
        return list(active.values())

    def review_incident(self, identity, rationale="", revision=None, actor="local-operator"):
        self.refresh_incidents()
        item = self.incidents.get(identity)
        if item["restriction"] == "released":
            return item
        if not self.reconciled:
            raise Conflict("Complete paper attestation and reconciliation before recovery review.")
        if item["restriction"] != "ready_for_release":
            raise Conflict(item["recovery_detail"])
        if revision is not None and revision != item["revision"]:
            raise Conflict("Incident changed. Refresh its recovery review.")
        with self.store.transaction() as db:
            latest = self.incidents.get(item["id"], db)
            evidence, detail = self._incident_evidence(latest)
            if not evidence:
                raise Conflict(detail)
            result = self.incidents.release_in(
                db,
                item["id"],
                item["revision"],
                actor,
                rationale.strip() or "Operator acknowledged verified recovery.",
                evidence=evidence,
            )
        self._incident_stability.pop(item["id"], None)
        return result

    def incident_current(self):
        self.refresh_incidents()
        return self.incidents.page()

    def incident_page(self, view="current", before=None, limit=200):
        return self.incidents.page(view=view, before=before, limit=limit)

    def recovery_batch_preview(self):
        self.refresh_incidents()
        items = [
            incident_summary(i)
            for i in self.incidents.open()
            if i["review_policy"] == "arming" and i["restriction"] == "ready_for_release"
        ][:200]
        result = {
            "preview_id": uuid.uuid4().hex,
            "instance": self.process_identity,
            "epoch": self.broker.epoch,
            "items": items,
        }
        with self.store.transaction() as db:
            self.store.write(db, "recovery_preview", result["preview_id"], result)
            db.execute(
                "DELETE FROM documents WHERE kind='recovery_preview' AND rowid NOT IN "
                "(SELECT rowid FROM documents WHERE kind='recovery_preview' "
                "ORDER BY rowid DESC LIMIT 20)"
            )
        return result

    def recovery_status(self):
        self.refresh_incidents()
        rows = self.incidents.page()["items"]
        for item in rows:
            item["remaining_seconds"] = 0
        return {"items": rows, "automatic": self.automatic_recovery_enabled}

    def recovery_batch_confirm(self, preview_id, mutation_id, actor):
        self.refresh_incidents()
        with self.store.transaction() as db:
            prior = self.store.read(db, "recovery_receipt", mutation_id)
            if prior:
                if prior["preview_id"] != preview_id or prior["actor"] != actor:
                    raise Conflict("Action identifier already used for another recovery request.")
                return prior["result"]
            preview = self.store.read(db, "recovery_preview", preview_id)
            owner = self.store.read(db, "workspace", "engine_owner") or {}
            if (
                not preview
                or preview["instance"] != self.process_identity
                or owner.get("instance") != self.process_identity
                or owner.get("state") == "stopped"
                or preview["epoch"] != self.broker.epoch
                or not self.reconciled
            ):
                raise Conflict("Recovery review expired or connection changed. Review again.")
            if not preview["items"]:
                raise Conflict("No verified routine recoveries in this review.")
            released = []
            for reviewed in preview["items"]:
                item = self.incidents.get(reviewed["id"], db)
                if (
                    item["revision"] != reviewed["revision"]
                    or item["review_policy"] != "arming"
                    or item["restriction"] != "ready_for_release"
                ):
                    raise Conflict("A reviewed incident changed. Review the recovery batch again.")
                evidence, detail = self._incident_evidence(item)
                stable = self._incident_stability.get(item["id"])
                if not evidence or not stable or time.monotonic() - stable[2] > 10:
                    raise Conflict(detail or "Recovery stability expired. Review again.")
                self.incidents.release_in(
                    db,
                    item["id"],
                    item["revision"],
                    actor,
                    "Operator acknowledged verified routine recovery batch.",
                    evidence=evidence,
                )
                released.append(item["id"])
            result = {"released": released}
            self.store.write(
                db,
                "recovery_receipt",
                mutation_id,
                {"preview_id": preview_id, "actor": actor, "result": result},
            )
        self._overview_cache = None
        return result

    def incident_detail(self, identity):
        self.refresh_incidents()
        item = self.incidents.get(identity)
        item = self.current_condition(item)
        item["automatic_release_enabled"] = self.automatic_recovery_enabled
        if item["restriction"] == "released":
            return item
        with self.store.connect() as db:
            retired = self.automatic_recovery_enabled and self.unused_feed(item, db)
        item["dependency_relevance"] = "unused" if retired else "required_or_unproven"
        remaining = 0
        checks = self._recovery_checks(item, retired)
        checks.append(
            {
                "code": "reconciliation_complete",
                "title": "Reconciliation complete",
                "passed": bool(self.reconciled),
                "detail": "Wait for any in-progress reconciliation to finish.",
            }
        )
        item["recovery"] = {
            "checks": checks,
            "checked_at": datetime.now().astimezone().isoformat(),
            "remaining_seconds": remaining,
            "can_release": item["restriction"] == "ready_for_release"
            and all(c["passed"] for c in checks),
        }
        if item["scope"]["type"] == "contract":
            conid = int(item["scope"]["key"])
            item["feeds"] = {"conid": conid, "components": self.feed_projection(conid)}
        return item

    def close_investigation(self, identity, revision, rationale, actor):
        return self.incidents.close_investigation(identity, revision, actor, rationale)

    def incident_recoveries(self, runs):
        return [
            {**incident_summary(i), "evidence": i.get("evidence")}
            for i in self.incidents.applicable(runs)
            if i["restriction"] == "ready_for_release"
        ]

    def _flush_incident_cancellations(self):
        from .dependencies import operation_active

        for pending in self.store.list("incident_cancel"):
            if not operation_active("incident_cancel", pending):
                continue
            if not pending.get("run_id"):
                self.incident(
                    "engine_fault", "An active cancellation operation has no run identity."
                )
                continue
            key = pending["run_id"]
            for order in self.store.orders(active_only=True):
                if order["run_id"] == key and order["payload"].get("purpose", "entry") == "entry":
                    if order["state"] == "reserved":
                        with self.store.transaction() as db:
                            db.execute(
                                "UPDATE outbox SET state='cancelled' "
                                "WHERE id=? AND state='reserved'",
                                (order["id"],),
                            )
                            reservation = self.store.read(db, "reservation", order["id"])
                            if reservation:
                                self.store.write(
                                    db, "reservation", order["id"], {**reservation, "active": False}
                                )
                                self.store.append(
                                    db,
                                    "risk.released",
                                    {"id": order["id"], "reason": "incident_before_submission"},
                                )
                            self.store.append(
                                db,
                                "order.dispatch.blocked",
                                {"id": order["id"], "never_submitted": True},
                            )
                            group = self.store.read(db, "oca_group", order["id"])
                            if group:
                                self.store.write(
                                    db, "oca_group", order["id"], {**group, "state": "cancelled"}
                                )
                        continue
                    self.cancel_entry(order["id"], reason="incident_restriction")
            with self.store.transaction() as db:
                db.execute("DELETE FROM documents WHERE kind='incident_cancel' AND id=?", (key,))
