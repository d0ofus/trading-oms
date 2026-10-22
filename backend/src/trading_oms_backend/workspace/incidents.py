"""Audited incident episodes and indexed trading restrictions; no broker capabilities."""

import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path

from .graph import canonical, number
from .store import Conflict, now

POLICY_VERSION = 5
ROUTINE = {"watchdog", "connectivity", "broker_2110"}
SERVICE_RECOVERY = {"broker_2103": 2104, "broker_2105": 2106, "broker_2157": 2158}
CONTRACT_CODES = {
    "market_data_failure",
    "history_timeout",
    "warmup_overflow",
    "quote_feed_failure",
    "trade_feed_failure",
    "history_feed_failure",
    "regular_history_feed_failure",
    "premarket_history_feed_failure",
    "data_request_failure",
}
STRATEGY_CODES = {"strategy_evaluation"}
RUN_CODES = {"run_configuration", "premarket_exit_pending"}
ACCOUNT_CODES = {
    "broker_credit_shortfall",
    "fx_account_balance",
    "fx_ownership",
    "missing_protection",
    "protection_rejected",
    "protection_uncertain",
    "foreign_account",
    "account_context",
    "execution_conflict",
    "unknown_order",
    "external_order",
}


def routine_policy(code, scope, diagnostic=None):
    return (
        code in ROUTINE
        or code in SERVICE_RECOVERY
        or (code in CONTRACT_CODES and scope["type"] == "contract")
    )


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS incident_totals "
    "(restriction TEXT PRIMARY KEY,total INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS incident_episodes ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,code TEXT NOT NULL,"
    "scope_type TEXT NOT NULL,scope_key TEXT NOT NULL,restriction TEXT NOT NULL,"
    "investigation TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,"
    "correlation_key TEXT NOT NULL DEFAULT '')",
    "CREATE UNIQUE INDEX IF NOT EXISTS incident_open_identity ON incident_episodes"
    "(code,scope_type,scope_key,correlation_key) WHERE restriction!='released'",
    "CREATE INDEX IF NOT EXISTS incident_scope ON incident_episodes"
    "(scope_type,scope_key,restriction)",
    "CREATE INDEX IF NOT EXISTS incident_restriction_page ON incident_episodes"
    "(restriction,sequence)",
    "CREATE INDEX IF NOT EXISTS incident_code ON incident_episodes(code,sequence)",
    "CREATE INDEX IF NOT EXISTS incident_episode_history ON incident_episodes"
    "(code,scope_type,scope_key,sequence)",
    "CREATE INDEX IF NOT EXISTS incident_active_scope ON incident_episodes"
    "(scope_type,scope_key) WHERE restriction!='released'",
    "CREATE INDEX IF NOT EXISTS incident_investigation ON incident_episodes"
    "(investigation,restriction,sequence)",
)


def safe_fault(exc, operation, observation=None):
    """Only class and code locations; exception strings/source lines/locals are private."""
    frames = []
    tb = exc.__traceback__
    while tb:
        code = tb.tb_frame.f_code
        name = Path(code.co_filename).name
        frames.append({"file": name[:100], "function": code.co_name[:100], "line": tb.tb_lineno})
        tb = tb.tb_next
    result = {
        "exception_class": type(exc).__name__[:100],
        "operation": operation[:80],
        "observation": observation,
        "frames": frames[-8:],
    }
    result["fingerprint"] = hashlib.sha256(canonical(result).encode()).hexdigest()[:24]
    return result


def scope_for(code, *, conid=None, run=None):
    if code in CONTRACT_CODES and type(conid) is int and conid > 0:
        return {"type": "contract", "key": str(conid)}
    if code in STRATEGY_CODES and run and run.get("strategy_id") and run.get("version"):
        return {"type": "strategy", "key": f"{run['strategy_id']}:{run['version']}"}
    if code in RUN_CODES and run and run.get("id"):
        return {"type": "run", "key": run["id"]}
    return {"type": "account" if code in ACCOUNT_CODES else "workspace", "key": "*"}


def affects(item, run):
    plan = (run.get("binding") or {}).get("execution_plan", {})
    if (
        plan.get("signal_source")
        or plan.get("requirements", {}).get("kind") in {"fx_breakout", "stock_breakout"}
    ) and (
        "history" in item["code"]
        or item["code"] == "broker_2105"
        or item["code"] == "history_timeout"
        or item["code"] == "data_request_failure"
        and "history" in (item.get("diagnostic") or {}).get("operation", "")
    ):
        return False  # This FX definition builds its reference exclusively live.
    diagnostic = item.get("diagnostic") or {}
    if diagnostic.get("fx") and diagnostic.get("signal_source") not in {None, "fx_bidask"}:
        source = diagnostic["signal_source"]
        source = "MIDPOINT" if source == "fx_midpoint" else source
        if (run.get("binding") or {}).get("execution_plan", {}).get("signal_source") != source:
            return False
    if item["code"] == "premarket_history_feed_failure":
        from .premarket import premarket

        if not premarket(run):
            return False
    if item["code"] == "regular_history_feed_failure":
        from .premarket import premarket

        if premarket(run):
            return False
    scope = item["scope"]
    return (
        scope["type"] in {"workspace", "account"}
        or (scope["type"] == "contract" and scope["key"] == str(run.get("conid")))
        or (scope["type"] == "run" and scope["key"] == run.get("id"))
        or (
            scope["type"] == "strategy"
            and scope["key"] == f"{run.get('strategy_id')}:{run.get('version')}"
        )
    )


def incident_summary(item):
    return {
        k: v
        for k, v in item.items()
        if k not in {"diagnostic", "evidence", "release_evidence", "decisions"}
    }


def clear_notifications(store, db, item):
    notifications = db.execute(
        "SELECT id,payload FROM documents WHERE kind='notification' "
        "AND json_extract(payload,'$.incident_id')=?",
        (item["id"],),
    ).fetchall()
    delivered = False
    for row in notifications:
        notice = json.loads(row["payload"])
        delivered = delivered or notice.get("state") == "delivered"
        if notice.get("state") == "queued":
            store.write(
                db,
                "notification",
                row["id"],
                {**notice, "state": "superseded", "reason": "condition_recovered"},
            )
    if delivered and item.get("severity") == "critical":
        key = uuid.uuid4().hex
        store.write(
            db,
            "notification",
            key,
            {
                "id": key,
                "incident_id": item["id"],
                "state": "queued",
                "attempts": 0,
                "created_at": now(),
                "text": "Trading concern resolved after verified recovery: " + item["code"],
                "recovery": True,
            },
        )


class IncidentBook:
    def __init__(self, store):
        self.store = store
        self._migrate()
        self._migrate_correlation()
        self._migrate_review_policy()

    def _migrate_review_policy(self):
        if (self.store.get("workspace", "routine_review_policy") or {}).get(
            "version", 0
        ) >= POLICY_VERSION:
            return
        self.store.backup(self.store.directory / "backups")
        with self.store.transaction() as db:
            if (self.store.read(db, "workspace", "routine_review_policy") or {}).get(
                "version", 0
            ) >= POLICY_VERSION:
                return
            for item in self.open(db):
                from .current_conditions import classification

                category, severity = classification(item["code"])
                policy = (
                    "arming"
                    if routine_policy(item["code"], item["scope"], item.get("diagnostic"))
                    else "dedicated"
                )
                release_policy = "automatic" if policy == "arming" else "manual"
                if (
                    item["review_policy"] == policy
                    and item.get("release_policy") == release_policy
                    and item.get("category") == category
                    and item.get("severity") == severity
                ):
                    continue
                item.update(
                    review_policy=policy,
                    release_policy=release_policy,
                    policy_version=POLICY_VERSION,
                    category=category,
                    severity=severity,
                    revision=item["revision"] + 1,
                )
                self._save(db, item)
                self.store.append(db, "incident.review_policy.changed", incident_summary(item))
            for row in db.execute(
                "SELECT id,payload FROM documents WHERE kind='notification'"
            ).fetchall():
                notice = json.loads(row["payload"])
                if notice.get("state") != "queued" or not notice.get("incident_id"):
                    continue
                episode = db.execute(
                    "SELECT payload FROM incident_episodes WHERE id=?", (notice["incident_id"],)
                ).fetchone()
                if episode:
                    item = json.loads(episode[0])
                    if item["restriction"] == "released" or (
                        routine_policy(item["code"], item["scope"]) and item["code"] != "watchdog"
                    ):
                        self.store.write(
                            db,
                            "notification",
                            row["id"],
                            {**notice, "state": "superseded", "reason": "current_condition_policy"},
                        )
            self.store.write(db, "workspace", "routine_review_policy", {"version": POLICY_VERSION})

    def _migrate_correlation(self):
        with self.store.connect() as db:
            if any(
                row[1] == "correlation_key"
                for row in db.execute("PRAGMA table_info(incident_episodes)")
            ):
                return
            directory = self.store.directory / "backups"
            directory.mkdir(exist_ok=True)
            with sqlite3.connect(
                directory / f"incident-correlation-{uuid.uuid4().hex}.sqlite3"
            ) as backup:
                db.backup(backup)
        with self.store.transaction() as db:
            if any(
                row[1] == "correlation_key"
                for row in db.execute("PRAGMA table_info(incident_episodes)")
            ):
                return
            db.execute(
                "ALTER TABLE incident_episodes ADD COLUMN correlation_key TEXT NOT NULL DEFAULT ''"
            )
            db.execute("DROP INDEX incident_open_identity")
            db.execute(
                "CREATE UNIQUE INDEX incident_open_identity ON incident_episodes "
                "(code,scope_type,scope_key,correlation_key) WHERE restriction!='released'"
            )
            self.store.append(
                db,
                "incident.correlation.migration",
                {"backup_created": True, "automatic_release": False},
            )

    def _migrate(self):
        with self.store.connect() as db:
            done = db.execute("SELECT 1 FROM metadata WHERE key='incident_schema_v1'").fetchone()
            legacy = (
                []
                if done
                else db.execute("SELECT payload FROM documents WHERE kind='incident'").fetchall()
            )
            existing = not done and any(
                db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                for table in ("documents", "events", "versions")
            )
            if existing:
                directory = self.store.directory / "backups"
                directory.mkdir(exist_ok=True)
                target = directory / f"incident-migration-{uuid.uuid4().hex}.sqlite3"
                with sqlite3.connect(target) as backup:
                    db.backup(backup)
        if done:
            return
        with self.store.transaction() as db:
            for statement in SCHEMA:
                db.execute(statement)
            for row in legacy:
                self.import_legacy_in(db, json.loads(row["payload"]))
            db.execute("INSERT OR IGNORE INTO metadata VALUES('incident_schema_v1','1')")
            if existing:
                self.store.append(
                    db,
                    "incident.migration",
                    {
                        "policy_version": POLICY_VERSION,
                        "records": len(legacy),
                        "backup_created": True,
                        "automatic_release": False,
                    },
                )

    def import_legacy_in(self, db, legacy):
        code = legacy.get("id", "unknown_legacy")
        if db.execute("SELECT 1 FROM incident_episodes WHERE code=?", (code,)).fetchone():
            return
        stamp = legacy.get("timestamp") or now()
        released = legacy.get("resolved") is True
        item = {
            "id": uuid.uuid4().hex,
            "code": code,
            "scope": scope_for(code),
            "condition": "recovered" if released else "unknown",
            "restriction": "released" if released else "held",
            "investigation": "open",
            "review_policy": "arming" if code in ROUTINE else "dedicated",
            "revision": 1,
            "occurrences": 1,
            "first_at": stamp,
            "last_at": stamp,
            "timestamp": stamp,
            "instance": legacy.get("instance"),
            "origin_instance": legacy.get("instance"),
            "detail": legacy.get("detail", "Legacy incident requires current recovery evidence."),
            "severity": legacy.get("severity", "critical"),
            "legacy": True,
            "policy_version": POLICY_VERSION,
            "evidence": None,
            "recovery_detail": "Legacy evidence must be checked against the current engine.",
            "failure_sequence": self._watermark(db),
            "resolved": released,
        }
        self._save(db, item)
        self.store.append(db, "incident.episode.imported", incident_summary(item))

    @staticmethod
    def _watermark(db):
        return db.execute("SELECT COALESCE(MAX(sequence),0) FROM events").fetchone()[0]

    def watermark(self):
        with self.store.connect() as db:
            return self._watermark(db)

    def _save(self, db, item):
        item["resolved"] = item["restriction"] == "released"
        prior = db.execute(
            "SELECT restriction FROM incident_episodes WHERE id=?", (item["id"],)
        ).fetchone()
        if not prior or prior[0] != item["restriction"]:
            if prior:
                db.execute(
                    "UPDATE incident_totals SET total=total-1 WHERE restriction=?", (prior[0],)
                )
            db.execute(
                "INSERT INTO incident_totals VALUES(?,1) ON CONFLICT(restriction) "
                "DO UPDATE SET total=total+1",
                (item["restriction"],),
            )
        db.execute(
            "INSERT INTO incident_episodes(id,code,scope_type,scope_key,restriction,"
            "investigation,revision,payload,correlation_key) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "restriction=excluded.restriction,investigation=excluded.investigation,"
            "revision=excluded.revision,payload=excluded.payload",
            (
                item["id"],
                item["code"],
                item["scope"]["type"],
                item["scope"]["key"],
                item["restriction"],
                item["investigation"],
                item["revision"],
                canonical(item),
                item.get("correlation_key", ""),
            ),
        )
        latest = db.execute(
            "SELECT payload FROM incident_episodes WHERE code=? AND restriction!='released' "
            "ORDER BY sequence DESC LIMIT 1",
            (item["code"],),
        ).fetchone()
        if latest is None:
            latest = db.execute(
                "SELECT payload FROM incident_episodes WHERE code=? ORDER BY sequence DESC LIMIT 1",
                (item["code"],),
            ).fetchone()
        mirror = json.loads(latest["payload"])
        self.store.write(
            db,
            "incident",
            item["code"],
            {
                **mirror,
                "episode_id": mirror["id"],
                "id": item["code"],
            },
        )

    def raise_incident(self, code, detail, instance, **context):
        with self.store.transaction() as db:
            return self.raise_in(db, code, detail, instance, **context)

    def raise_in(
        self,
        db,
        code,
        detail,
        instance,
        *,
        conid=None,
        run=None,
        diagnostic=None,
        notify=True,
        correlation_key="",
        order_context=None,
        rejection=None,
        refinement=False,
        new_failure=False,
        connection_epoch=None,
    ):
        if correlation_key and not re.fullmatch(r"[a-zA-Z0-9_:-]{1,120}", correlation_key):
            raise ValueError("Invalid internal incident correlation key.")
        scope = scope_for(code, conid=conid, run=run)
        if order_context and order_context.get("run_id"):
            scope = {"type": "run", "key": order_context["run_id"]}
        row = db.execute(
            "SELECT payload FROM incident_episodes WHERE code=? AND scope_type=? AND scope_key=? "
            "AND correlation_key=? AND restriction!='released'",
            (code, scope["type"], scope["key"], correlation_key),
        ).fetchone()
        stamp = now()
        new_episode = row is None
        if row:
            item = json.loads(row["payload"])
            if (
                not refinement
                and not new_failure
                and item.get("condition") == "active"
                and item.get("instance") == instance
                and item.get("connection_epoch") == connection_epoch
                and item.get("detail") == detail[:1000]
                and item.get("diagnostic") == diagnostic
            ):
                return item  # Identical callback supplies no new failure evidence.
            if code == "engine_fault":
                from .fault_policy import record_faults

                record_faults(item, diagnostic, item["occurrences"])
            item.update(
                revision=item["revision"] + 1,
                occurrences=item["occurrences"] + (0 if refinement else 1),
            )
        else:
            from .current_conditions import classification

            category, severity = classification(code)
            previous = db.execute(
                "SELECT id FROM incident_episodes WHERE code=? AND scope_type=? AND scope_key=? "
                "AND correlation_key=? ORDER BY sequence DESC LIMIT 1",
                (code, scope["type"], scope["key"], correlation_key),
            ).fetchone()
            item = {
                "id": uuid.uuid4().hex,
                "code": code,
                "scope": scope,
                "revision": 1,
                "occurrences": 1,
                "first_at": stamp,
                "origin_instance": instance,
                "investigation": "open",
                "review_policy": "arming"
                if routine_policy(code, scope, diagnostic)
                else "dedicated",
                "policy_version": POLICY_VERSION,
                "category": category,
                "severity": severity,
                "previous_episode": previous["id"] if previous else None,
            }
            if correlation_key:
                item["correlation_key"] = correlation_key
            if code == "engine_fault":
                from .fault_policy import record_faults

                record_faults(item, diagnostic, 0)
        if order_context is not None:
            item["order_context"] = order_context
        if rejection is not None:
            item["rejection"] = rejection
        item.update(
            condition="active",
            restriction="held",
            detail=detail[:1000],
            instance=instance,
            connection_epoch=connection_epoch,
            release_policy="automatic" if routine_policy(code, scope, diagnostic) else "manual",
            last_at=stamp,
            timestamp=stamp,
            evidence=None,
            recovery_detail="The failure requires current recovery evidence.",
            failure_sequence=self._watermark(db) + 1,
        )
        changed_diagnostic = diagnostic and diagnostic != item.get("diagnostic")
        if diagnostic:
            item["diagnostic"] = diagnostic
        self._save(db, item)
        self.store.append(
            db,
            "incident.raised"
            if not row
            else "incident.refined"
            if refinement
            else "incident.observed",
            {
                **incident_summary(item),
                **({"diagnostic": diagnostic} if changed_diagnostic else {}),
            },
        )
        # Authorizations are revoked in the same transaction, including independent alerts.
        pending_runs = {
            row[0]
            for row in db.execute(
                "SELECT DISTINCT run_id FROM outbox "
                "WHERE state NOT IN ('filled','cancelled','rejected') "
                "AND COALESCE(json_extract(payload,'$.purpose'),'entry')='entry'"
            )
        }
        from .authorization import resumable_failure

        for row in db.execute("SELECT id,payload FROM documents WHERE kind='run'").fetchall():
            target = json.loads(row["payload"])
            if code == "broker_notice":
                continue
            if affects(item, target) and (
                target.get("armed")
                or target.get("authorization_status") == "temporarily_suspended"
                or row["id"] in pending_runs
            ):
                suspended = resumable_failure(target, item, instance)
                target.update(
                    armed=False,
                    authorization_status="temporarily_suspended" if suspended else "revoked",
                    state="position_open"
                    if number(target.get("position", "0")) != 0
                    else "suspended"
                    if suspended
                    else "paused",
                    blocking_reason=detail[:1000],
                )
                self.store.write(db, "run", row["id"], target)
                self.store.append(
                    db,
                    "run.authorization.suspended" if suspended else "run.disarmed",
                    {"run_id": row["id"], "incident": item["id"]},
                )
                if not suspended or row["id"] in pending_runs:
                    self.store.write(db, "incident_cancel", row["id"], {"run_id": row["id"]})
        if notify and new_episode and item["severity"] == "critical":
            identity = uuid.uuid4().hex
            self.store.write(
                db,
                "notification",
                identity,
                {
                    "id": identity,
                    "text": detail[:1000],
                    "state": "queued",
                    "created_at": stamp,
                    "attempts": 0,
                    "incident_id": item["id"],
                },
            )
        return item

    def reclassify_informational_in(self, db, code):
        if code != "broker_2119":
            raise Conflict("Only the audited 2119 informational correction is supported.")
        for row in db.execute(
            "SELECT payload FROM incident_episodes WHERE code=? AND restriction!='released'",
            (code,),
        ).fetchall():
            item = json.loads(row[0])
            item.update(
                condition="recovered",
                restriction="released",
                investigation="closed",
                revision=item["revision"] + 1,
                release_actor="classification-policy",
                release_reason="Informational farm connection message",
                released_at=now(),
            )
            self._save(db, item)
            self.store.append(db, "incident.reclassified", item)

    def open(self, db=None):
        if db is None:
            with self.store.connect() as connection:
                return self.open(connection)
        return [
            json.loads(r[0])
            for r in db.execute(
                "SELECT payload FROM incident_episodes "
                "WHERE restriction IN ('held','ready_for_release')"
            )
        ]

    def applicable(self, runs=None, db=None):
        if runs is None:
            return self.current(self.open(db), runs, db)
        if db is None:
            with self.store.connect() as connection:
                return self.applicable(runs, connection)
        clauses = ["scope_type IN ('workspace','account')"]
        values = []
        for run in runs:
            clauses += ["(scope_type=? AND scope_key=?)"] * 3
            values += [
                "contract",
                str(run.get("conid")),
                "run",
                run.get("id", ""),
                "strategy",
                f"{run.get('strategy_id')}:{run.get('version')}",
            ]
        rows = db.execute(
            "SELECT payload FROM incident_episodes WHERE restriction!='released' AND ("
            + " OR ".join(clauses)
            + ")",
            values,
        )
        items = [json.loads(r[0]) for r in rows]
        return self.current(
            [
                item
                for item in items
                if item["scope"]["type"] in {"workspace", "account"}
                or any(affects(item, run) for run in runs)
            ],
            runs,
            db,
        )

    def current(self, items, runs=None, db=None):
        evaluator = getattr(self, "current_evaluator", None)
        if evaluator is None:
            return items
        projected = [evaluator(item, runs, db) for item in items]
        return [item for item in projected if item["actionable"]]

    def get(self, identity, db=None):
        if db is None:
            with self.store.connect() as connection:
                return self.get(identity, connection)
        row = db.execute("SELECT payload FROM incident_episodes WHERE id=?", (identity,)).fetchone()
        if row:
            return json.loads(row[0])
        rows = db.execute(
            "SELECT payload FROM incident_episodes WHERE code=? AND restriction!='released'",
            (identity,),
        ).fetchall()
        if len(rows) != 1:
            raise Conflict(
                "Select a specific current incident episode; the code is absent or ambiguous."
            )
        return json.loads(rows[0][0])

    def recover_in(self, db, item, evidence):
        latest = self.get(item["id"], db)
        if latest["revision"] != item["revision"]:
            raise Conflict("Incident changed while recovery was evaluated.")
        if latest["restriction"] == "ready_for_release":
            return latest
        latest.update(
            condition="recovered",
            restriction="ready_for_release",
            recovered_at=now(),
            evidence=evidence,
            recovery_detail="Recovery verified. Explicit operator acknowledgment is required.",
            revision=latest["revision"] + 1,
        )
        self._save(db, latest)
        self.store.append(db, "incident.recovered", latest)
        return latest

    def withhold_in(self, db, item, detail):
        latest = self.get(item["id"], db)
        if latest["restriction"] == "released":
            return latest
        if latest["restriction"] == "ready_for_release":
            latest.update(
                condition="unknown",
                restriction="held",
                evidence=None,
                revision=latest["revision"] + 1,
            )
            self.store.append(
                db, "incident.recovery.withdrawn", {"id": latest["id"], "reason": detail}
            )
        if latest.get("recovery_detail") != detail or latest != item:
            latest["recovery_detail"] = detail
            self._save(db, latest)
        return latest

    def release_in(self, db, identity, revision, actor, rationale, evidence=None):
        item = self.get(identity, db)
        if (
            item["revision"] != revision
            or item["restriction"] != "ready_for_release"
            or item["condition"] != "recovered"
        ):
            raise Conflict("Incident recovery changed or remains blocked. Refresh the review.")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", actor):
            raise Conflict("An authenticated operator audit identity is required.")
        item.update(
            restriction="released",
            released_at=now(),
            revision=item["revision"] + 1,
            release_actor=actor,
            release_reason=rationale[:1000],
            release_evidence=evidence,
        )
        self._save(db, item)
        self.store.append(db, "incident.reviewed", item)
        clear_notifications(self.store, db, item)
        return item

    def page(self, *, view="current", before=None, limit=200):
        if (
            view not in {"current", "history", "investigations", "diagnostics"}
            or not 1 <= limit <= 200
        ):
            raise ValueError("Choose a bounded current, history or investigations page.")
        where = {
            "current": "restriction IN ('held','ready_for_release')",
            "history": "restriction='released'",
            "investigations": "restriction='released' AND investigation='open'",
            "diagnostics": "1=1",
        }[view]
        items = []
        cursor = before or 9223372036854775807
        with self.store.connect() as db:
            while len(items) <= limit:
                rows = db.execute(
                    f"SELECT sequence,payload FROM incident_episodes WHERE {where} AND sequence<? "
                    "ORDER BY sequence DESC LIMIT ?",
                    (cursor, 200),
                ).fetchall()
                for row in rows:
                    item = json.loads(row["payload"])
                    projected = self.current([item], db=db) if view == "current" else [item]
                    if projected:
                        items.append((row["sequence"], projected[0]))
                    if len(items) > limit:
                        break
                if len(rows) < 200 or len(items) > limit:
                    break
                cursor = rows[-1]["sequence"]
        return {
            "items": [incident_summary(i) for _, i in items[:limit]],
            "next_cursor": items[limit - 1][0] if len(items) > limit else None,
        }

    def close_investigation(self, identity, revision, actor, rationale):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", actor):
            raise Conflict("An authenticated operator audit identity is required.")
        if len(rationale.strip()) < 10:
            raise Conflict("Record the investigation outcome in at least 10 characters.")
        with self.store.transaction() as db:
            item = self.get(identity, db)
            if item["revision"] != revision or item["restriction"] != "released":
                raise Conflict(
                    "Release the verified trading restriction before closing its investigation."
                )
            item.update(
                investigation="closed",
                revision=item["revision"] + 1,
                investigation_closed_at=now(),
                investigation_actor=actor,
                investigation_outcome=rationale.strip()[:1000],
            )
            self._save(db, item)
            self.store.append(db, "incident.investigation.closed", item)
            return item

    def counts(self):
        with self.store.connect() as db:
            counts = {
                r[0]: r[1] for r in db.execute("SELECT restriction,total FROM incident_totals")
            }
            if getattr(self, "current_evaluator", None):
                current = self.current(self.open(db), db=db)
                counts.update(
                    {
                        k: sum(i["restriction"] == k for i in current)
                        for k in ("held", "ready_for_release")
                    }
                )
            return counts
