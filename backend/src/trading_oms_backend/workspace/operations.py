"""Operator lifecycle actions executed only by the engine owner."""

import time
from datetime import UTC, datetime, timedelta

from .graph import digest, number
from .protection import TERMINAL, order_ids
from .qualification import qualification_checks
from .store import Conflict, now


class OperatorActions:
    def legacy_extended_history(self, conid):
        for run in self.store.list("run"):
            if (
                run.get("conid") != conid
                or run.get("archived")
                or not run.get("strategy_id")
                or not run.get("version")
            ):
                continue
            document = self.store.version(run["strategy_id"], run["version"])["document"]
            if document["settings"].get("trading_hours") == "extended":
                return True
        return False

    def _flexible_selection(self, ids, session_date):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 5 or len(set(ids)) != len(ids):
            raise ValueError("Select one to five distinct runs.")
        versions = []
        for key in ids:
            run = self.store.get("run", key)
            if not run:
                raise ValueError("A selected run no longer exists.")
            if run.get("archived"):
                raise Conflict("Archived runs cannot be armed. Prepare a new run.")
            versions.append(self.store.version(run["strategy_id"], run["version"])["document"])
        requested = session_date is not None or any(
            "trading_hours" in d["settings"] for d in versions
        )
        if requested and (
            self.environment.crypto
            or any(
                d["schema_version"] not in (3, 4) or d["settings"].get("instrument_profile")
                for d in versions
            )
        ):
            raise Conflict(
                "Scheduled stock sessions require legacy stock versions. "
                "Reusable stock, FX and crypto retain their own session policies."
            )
        return requested

    def _flexible_preview(
        self, ids, profile_id="smoke", profile_version=1, unattended=False, session_date=None
    ):
        from .engine import check

        self.refresh_incidents()
        if not isinstance(ids, list) or not 1 <= len(ids) <= 5 or len(set(ids)) != len(ids):
            raise ValueError("Select one to five distinct runs.")
        checks = self.readiness()
        if profile_version is None:
            profile_version = max(
                (p["version"] for p in self.store.list("risk_profile") if p["id"] == profile_id),
                default=1,
            )
        profile = self.store.get("risk_profile", f"{profile_id}:{profile_version}")
        if not profile:
            raise ValueError("Select a published risk profile.")
        if "shares" not in profile or "daily_loss" in profile:
            raise Conflict("Select a current legacy stock risk profile.")
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
            from .contracts import execution_reason

            reason = execution_reason(
                self.contracts.get(run["conid"], {}),
                self.store.version(run["strategy_id"], run["version"])["document"],
            )
            checks.append(
                check(
                    "capability_" + key,
                    "Qualified stock contract",
                    reason is None and self._binding_valid(run),
                    reason or "Contract identity matches its approved binding.",
                )
            )
            data = self.data.get(run["conid"], {})
            fresh = (
                data.get("received_at")
                and 0
                <= (datetime.now(UTC) - datetime.fromisoformat(data["received_at"])).total_seconds()
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
        restrictions = self.incidents.applicable(selected)
        fingerprint = digest(
            {
                "instance": self.process_identity,
                "context": getattr(self, "paper_context_token", None),
                "runs": selected,
                "profile": profile,
                "unattended": unattended,
                "session_date": session_date,
            }
        )
        return {
            "flexible_session": True,
            "environment": self.environment.name,
            "session_policy": "xnys",
            "review_instance": self.process_identity,
            "review_fingerprint": fingerprint,
            "recoveries": self.incident_recoveries(selected),
            "eligible_after_recovery_ack": False,
            "can_authorize": all(c["passed"] for c in checks),
            "can_dispatch": all(c["passed"] for c in checks)
            and not any(r["valid_from"] > stamp.isoformat() for r in selected),
            "restrictions": restrictions,
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

    def removal_preview(self, key):
        run = self.store.get("run", key)
        if not run:
            raise ValueError("Run not found.")
        orders = [o for o in self.store.orders() if o["run_id"] == key]
        position = self.owned().get(key, {}).get("quantity", 0)
        reason = None
        if number(run.get("position", 0)) or position:
            reason = "Close the owned position and reconcile before removing this run."
        elif any(o["state"] in {"unknown", "dispatching", "reserved"} for o in orders):
            reason = "An order outcome is uncertain. Resolve it before removing this run."
        elif orders and (not self.reconciled or time.monotonic() - self.reconciled_at >= 30):
            reason = "Fresh broker reconciliation is required before removal."
        return {
            "eligible": reason is None,
            "reason": reason,
            "run": run,
            "will_cancel": any(o["state"] in {"working", "cancel_pending"} for o in orders),
        }

    def remove_run(self, key):
        preview = self.removal_preview(key)
        if not preview["eligible"]:
            raise Conflict(preview["reason"])
        run = preview["run"]
        if run.get("archived"):
            return run
        self.disarm(key, "Run removal requested.")
        run = self.store.get("run", key)
        run["removal_pending"] = True
        self.store.put("run", key, run)
        self.store.event("run.removal.requested", {"run_id": key})
        self._finish_removals()
        return self.store.get("run", key)

    def _finish_removals(self):
        for run in self.store.list("run"):
            if not run.get("removal_pending"):
                continue
            key = run["id"]
            orders = [o for o in self.store.orders() if o["run_id"] == key]
            if not self.removal_preview(key)["eligible"]:
                continue
            if any(o["state"] not in {"filled", "cancelled", "rejected"} for o in orders):
                continue
            if any((self.store.get("reservation", o["id"]) or {}).get("active") for o in orders):
                continue
            if any(
                (self.broker_orders.get(i) or self.store.get("broker_order", str(i)) or {}).get(
                    "status"
                )
                not in TERMINAL
                for o in orders
                for i in order_ids(o)
            ):
                continue
            if self.store.get("exit_request", key):
                continue
            with self.store.connect() as db:
                if self._archive_item(db, key)["reasons"]:
                    continue
            run.update(
                archived=True,
                archived_at=now(),
                removal_pending=False,
                state="completed",
                armed=False,
            )
            self.store.put("run", key, run)
            self.store.event("run.archived", {"run_id": key})
            self.runtime.pop(key, None)

    def _run_bounds(self, run, stamp=None):
        from .sessions import NY, execution_bounds

        stamp = stamp or datetime.now(UTC)
        return execution_bounds(
            run.get("session_date", stamp.astimezone(NY).date().isoformat()),
            run.get("trading_hours", "regular"),
            self.contracts.get(run["conid"]),
        )

    def _session_permission(self, run, stamp=None):
        if not run.get("valid_from"):
            return True  # Other versioned policies enforce their own session gates.
        stamp = stamp or datetime.now(UTC)
        bounds = self._run_bounds(run, stamp)
        return bool(
            bounds
            and bounds[0] <= stamp < bounds[1] - timedelta(minutes=15)
            and run.get("valid_from", "") <= stamp.isoformat() < run.get("expires_at", "")
        )
