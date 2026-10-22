from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .graph import canonical, compile_graph, digest


def now() -> str:
    return datetime.now(UTC).isoformat()


class Conflict(ValueError):
    pass


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS documents (
  kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (kind,id));
CREATE TABLE IF NOT EXISTS versions (
  strategy_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (strategy_id,version));
CREATE TABLE IF NOT EXISTS events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, type TEXT NOT NULL,
  payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'event ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'event ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_versions_update BEFORE UPDATE ON versions
  BEGIN SELECT RAISE(ABORT, 'published versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_versions_delete BEFORE DELETE ON versions
  BEGIN SELECT RAISE(ABORT, 'published versions are immutable'); END;
CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY, hash TEXT NOT NULL, payload TEXT NOT NULL, run_id TEXT NOT NULL,
  state TEXT NOT NULL, broker_id INTEGER NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions (
  id TEXT PRIMARY KEY, order_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS captures (
  id TEXT PRIMARY KEY, file TEXT NOT NULL, offset INTEGER NOT NULL, length INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_captures_update BEFORE UPDATE ON captures
  BEGIN SELECT RAISE(ABORT, 'capture manifests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_captures_delete BEFORE DELETE ON captures
  BEGIN SELECT RAISE(ABORT, 'capture manifests are immutable'); END;
"""


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "workspace.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript(SCHEMA)
            if (
                db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
                != "1"
            ):
                raise Conflict("Unsupported workspace schema. Restore a compatible build.")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None, factory=Connection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def transaction(self):
        with self.lock:
            db = self.connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def append(db, event_type: str, payload: dict):
        timestamp = now()
        previous = db.execute("SELECT hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        record_hash = digest([timestamp, event_type, payload, previous_hash])
        db.execute(
            "INSERT INTO events(timestamp,type,payload,previous_hash,hash) VALUES(?,?,?,?,?)",
            (timestamp, event_type, canonical(payload), previous_hash, record_hash),
        )

    def event(self, event_type: str, payload: dict):
        with self.transaction() as db:
            self.append(db, event_type, payload)

    def events(self, after=0, limit=200):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE sequence>? ORDER BY sequence LIMIT ?",
                (after, min(limit, 1000)),
            ).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    @staticmethod
    def read(db, kind, key):
        row = db.execute(
            "SELECT payload FROM documents WHERE kind=? AND id=?", (kind, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def write(db, kind, key, payload, revision=1):
        db.execute(
            "INSERT INTO documents VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE "
            "SET payload=excluded.payload,revision=excluded.revision",
            (kind, key, revision, canonical(payload)),
        )

    def get(self, kind, key):
        with self.connect() as db:
            return self.read(db, kind, key)

    def put(self, kind, key, payload):
        with self.transaction() as db:
            self.write(db, kind, key, payload)

    def list(self, kind):
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM documents WHERE kind=? ORDER BY rowid DESC", (kind,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_draft(self, key, name, document, expected):
        from .graph import CATALOG, number

        if (
            not isinstance(document, dict)
            or not isinstance(document.get("settings"), dict)
            or not isinstance(document.get("nodes"), list)
            or not isinstance(document.get("edges"), list)
        ):
            raise ValueError("Use a strategy document containing settings, nodes and connections.")
        if any(
            (not isinstance(v, (str, int, float)) or isinstance(v, bool))
            and not (
                document.get("schema_version") in (8, 9) and k in {"risk", "notional"} and v is None
            )
            for k, v in document["settings"].items()
        ):
            raise ValueError("Strategy settings require text or numeric values.")
        kinds = {item["kind"] for item in CATALOG}
        for node in document["nodes"]:
            if (
                not isinstance(node, dict)
                or not isinstance(node.get("id"), str)
                or node.get("kind") not in kinds
                or not isinstance(node.get("params"), dict)
                or not isinstance(node.get("label", ""), str)
            ):
                raise ValueError(
                    "Every draft block requires a supported type, identity and parameters."
                )
            if any(
                not isinstance(v, (str, int, float)) or isinstance(v, bool)
                for v in node["params"].values()
            ):
                raise ValueError("Block parameters require text or numeric values.")
            position = node.get("position", {"x": 0, "y": 0})
            if not isinstance(position, dict) or set(position) != {"x", "y"}:
                raise ValueError("Canvas positions require numeric x and y coordinates.")
            for value in position.values():
                number(value)
        if any(
            not isinstance(e, dict)
            or set(e) != {"source", "target", "input"}
            or not all(isinstance(v, str) for v in e.values())
            for e in document["edges"]
        ):
            raise ValueError("Connections require source, target and input names.")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Use a strategy name of 1–100 characters.")
        if len(canonical(document)) > 100_000:
            raise ValueError("Strategy is too large.")
        if document.get("schema_version") == 8 and not self.get("migration", "paper_stock_v2"):
            self.backup(self.directory / "backups")
            self.put(
                "migration",
                "paper_stock_v2",
                {"backed_up_at": now(), "historical_versions_unchanged": True},
            )
        if document.get("schema_version") == 9 and not self.get("migration", "paper_fx_v1"):
            self.backup(self.directory / "backups")
            self.put(
                "migration",
                "paper_fx_v1",
                {"backed_up_at": now(), "historical_versions_unchanged": True},
            )
        key = key or uuid.uuid4().hex
        with self.transaction() as db:
            from .library import require_available

            require_available(self, db, key)
            old = self.read(db, "draft", key)
            revision = old["revision"] if old else 0
            if revision != expected:
                raise Conflict("This draft changed elsewhere. Reload it before saving.")
            draft = {
                "id": key,
                "name": name.strip(),
                "document": document,
                "revision": revision + 1,
                "updated_at": now(),
                "published_version": old.get("published_version", 0) if old else 0,
            }
            self.write(db, "draft", key, draft, revision + 1)
            self.append(db, "strategy.draft.saved", {"id": key, "revision": revision + 1})
        return draft

    def publish(self, key, expected):
        with self.transaction() as db:
            from .library import require_available

            require_available(self, db, key)
            draft = self.read(db, "draft", key)
            if not draft or draft["revision"] != expected:
                raise Conflict("Reload the latest draft before publishing.")
            graph = compile_graph(draft["document"])
            version = db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM versions WHERE strategy_id=?", (key,)
            ).fetchone()[0]
            record = {
                "strategy_id": key,
                "name": draft["name"],
                "version": version,
                "document": graph.document,
                "hash": graph.digest,
                "explanation": graph.explain(),
                "published_at": now(),
                "compiler": "workspace-1",
            }
            db.execute("INSERT INTO versions VALUES(?,?,?)", (key, version, canonical(record)))
            draft["published_version"] = version
            draft["revision"] += 1
            self.write(db, "draft", key, draft, draft["revision"])
            self.append(
                db,
                "strategy.published",
                {"strategy_id": key, "version": version, "hash": graph.digest},
            )
        return record

    def version(self, key, version):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM versions WHERE strategy_id=? AND version=?", (key, version)
            ).fetchone()
        if not row:
            raise ValueError("Published strategy version not found.")
        return json.loads(row[0])

    def versions(self, key):
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM versions WHERE strategy_id=? ORDER BY version DESC", (key,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def emergency(self):
        return bool((self.get("safety", "emergency") or {}).get("active", False))

    def set_emergency(self, active):
        with self.transaction() as db:
            self.write(db, "safety", "emergency", {"active": active, "updated_at": now()})
            if active:
                rows = db.execute("SELECT id,payload FROM documents WHERE kind='run'").fetchall()
                for row in rows:
                    run = json.loads(row["payload"])
                    run["armed"] = False
                    run["state"] = "paused"
                    run["authorization_status"] = "revoked"
                    self.write(db, "run", row["id"], run)
            self.append(
                db, "emergency.activated" if active else "emergency.cleared", {"active": active}
            )

    def reserve_order(self, key, payload, run_id, next_id, reservation=None):
        from .oca import LEG_OFFSETS, is_pair

        payload = dict(payload)
        if is_pair(payload) and reservation is None:
            raise Conflict("A paired entry requires a combined risk reservation.")
        if (
            payload.get("execution") in {"crypto_breakout", "fx_breakout"}
            and payload.get("purpose") == "entry"
            and reservation is None
        ):
            raise Conflict("A currency paper entry requires a cash and stop-risk reservation.")
        if reservation is not None and payload.get("conid"):
            reservation = {**reservation, "conid": payload["conid"]}
        with self.transaction() as db:
            row = db.execute("SELECT * FROM outbox WHERE id=?", (key,)).fetchone()
            if row:
                if is_pair(payload) and "leg_ids" not in payload:
                    payload["leg_ids"] = json.loads(row["payload"])["leg_ids"]
                if row["hash"] != digest(payload):
                    raise Conflict("Order identity already belongs to a different payload.")
                return {**dict(row), "created": False}
            if payload.get("purpose", "entry") == "entry" and (
                self.read(db, "safety", "emergency") or {}
            ).get("active"):
                raise Conflict("Emergency stop blocks new entries.")
            if payload.get("purpose", "entry") == "entry" and (
                self.read(db, "run", run_id) or {}
            ).get("archived"):
                raise Conflict("Archived runs cannot create new entries.")
            if reservation is not None:
                from .graph import number

                run = self.read(db, "run", run_id)
                if (
                    not run
                    or not run.get("armed")
                    or run.get("valid_from", "") > now()
                    or run["expires_at"] <= now()
                ):
                    raise Conflict("A current session authorization is required.")
                existing = [
                    json.loads(r[0])
                    for r in db.execute("SELECT payload FROM documents WHERE kind='reservation'")
                ]
                active = [r for r in existing if r.get("active")]
                for existing_reservation in active:
                    owner = self.read(db, "run", existing_reservation.get("run_id", "")) or {}
                    existing_conid = existing_reservation.get("conid", owner.get("conid"))
                    conid = reservation.get("conid")
                    if (existing_conid and conid and existing_conid == conid) or (
                        (not existing_conid or not conid)
                        and existing_reservation["symbol"] == reservation["symbol"]
                    ):
                        raise Conflict(
                            "This contract already has reserved entry or position capacity."
                        )
                approved_plan = (run.get("binding") or {}).get("execution_plan") or {}
                from .credit import validate_reservation

                if approved_plan.get("funding_policy") != reservation.get("funding_policy"):
                    raise Conflict("Reservation funding policy differs from the approved binding.")
                validate_reservation(db, self, reservation)
                modern = approved_plan.get("risk_policy") == "paper_stock_v2"
                if modern and (
                    payload.get(
                        "fx_plan" if approved_plan.get("family") == "spot_fx" else "stock_plan"
                    )
                    != approved_plan
                    or payload.get("approved_sizing") != run["binding"]["sizing"]
                    or payload.get("risk_limits") != run["limits"]
                    or reservation.get("risk_policy") != "paper_stock_v2"
                    or run.get("limits", {}).get("risk_policy") != "paper_stock_v2"
                ):
                    raise Conflict("Reservation must match the authorized paper stock policy.")
                if (
                    len(active) >= 5
                    or not modern
                    and (
                        sum(number(r["risk"]) for r in active) + number(reservation["risk"]) > 50
                        or sum(number(r["notional"]) for r in active)
                        + number(reservation["notional"])
                        > 5000
                    )
                ):
                    raise Conflict("Shared paper risk capacity is exhausted.")
                if payload.get("fx_plan"):
                    if run.get("entries", 0) or run.get("authorization_status") != "authorized":
                        raise Conflict(
                            "This FX authorization has already consumed its entry or is suspended."
                        )
                    for currency, requested in (
                        {}
                        if reservation.get("funding_policy")
                        else reservation["currency_reserves"]
                    ).items():
                        outstanding = sum(
                            number(
                                r.get("currency_reserves", {}).get(
                                    currency,
                                    r.get("native_funds", 0)
                                    if r.get("currency") == currency
                                    else 0,
                                )
                            )
                            for r in active
                        )
                        if outstanding + number(requested) > number(
                            reservation["funding_snapshot"][currency]
                        ):
                            raise Conflict("Concurrent reservations exceed usable currency funds.")
                    if not self.read(db, "fx_ledger", "baseline"):
                        self.write(db, "fx_ledger", "baseline", payload["currency_baseline"])
                    protection = {
                        "run_id": run_id,
                        "entry_id": key,
                        "quantity": "0",
                        "stop": payload["stop"],
                        "type": payload["protection_type"],
                        "state": "awaiting_fill",
                    }
                    self.write(db, "fx_protection", run_id, protection)
                    self.append(db, "fx.protection.planned", protection)
                    run.update(
                        entries=run.get("entries", 0) + 1, state="entry_working", last_signal=now()
                    )
                    self.write(db, "run", run_id, run)
                    self.append(
                        db,
                        "authorization.consumed",
                        {
                            "run_id": run_id,
                            "authorization_id": run["authorization_id"],
                            "order_id": key,
                        },
                    )
                self.write(
                    db, "reservation", key, {**reservation, "active": True, "run_id": run_id}
                )
                self.append(db, "risk.reserved", {"id": key, **reservation})
            if payload.get("execution") == "crypto_breakout" and payload.get("purpose") == "entry":
                plan = {
                    "run_id": run_id,
                    "entry_id": key,
                    "quantity": "0",
                    "type": "locally_monitored",
                    "stop": payload["stop"],
                    "stop_ratio": "0.99",
                }
                self.write(db, "crypto_protection", run_id, plan)
                self.append(db, "crypto.protection.planned", plan)
            high_water = self.read(db, "allocator", "orders") or {}
            broker_id = max(
                next_id,
                high_water.get("next_id", 0),
                db.execute("SELECT COALESCE(MAX(broker_id),0)+3 FROM outbox").fetchone()[0],
            )
            if is_pair(payload):
                payload["leg_ids"] = {
                    name: broker_id + offset for name, offset in LEG_OFFSETS.items()
                }
            self.write(
                db, "allocator", "orders", {"next_id": broker_id + (4 if is_pair(payload) else 3)}
            )
            payload_hash = digest(payload)
            db.execute(
                "INSERT INTO outbox VALUES(?,?,?,?,?,?,?)",
                (key, payload_hash, canonical(payload), run_id, "reserved", broker_id, now()),
            )
            self.append(
                db,
                "order.intent.reserved",
                {"id": key, "run_id": run_id, "payload": payload, "broker_id": broker_id},
            )
            signal = self.read(db, "signal_outcome", run_id)
            if (
                payload.get("purpose", "entry") == "entry"
                and signal
                and signal.get("authorization_id") == run.get("authorization_id")
                and not signal.get("order_id")
            ):
                signal.update(
                    order_id=key,
                    state="checking",
                    updated_at=now(),
                    detail="Entry allocated; validating dispatch.",
                )
                self.write(db, "signal_outcome", run_id, signal)
                self.append(db, "signal.outcome", signal)
            if is_pair(payload):
                self.write(
                    db,
                    "oca_group",
                    key,
                    {
                        "id": key,
                        "run_id": run_id,
                        "state": "reserved",
                        "winner": None,
                        "candle": payload["candle"],
                        "leg_ids": payload["leg_ids"],
                        "authorization_id": run["authorization_id"],
                        "protection": "pending",
                        "counted": False,
                        "created_at": now(),
                    },
                )
            return {
                "id": key,
                "broker_id": broker_id,
                "state": "reserved",
                "created": True,
                **({"leg_ids": payload["leg_ids"]} if is_pair(payload) else {}),
            }

    def allocate_broker_id(self, next_id):
        """Reserve a non-reusable ID for a non-executing broker credit preview."""
        with self.transaction() as db:
            broker_id = max(
                next_id,
                (self.read(db, "allocator", "orders") or {}).get("next_id", 0),
                db.execute("SELECT COALESCE(MAX(broker_id),0)+4 FROM outbox").fetchone()[0],
            )
            self.write(db, "allocator", "orders", {"next_id": broker_id + 1})
            self.append(db, "broker.preview.id.allocated", {"broker_id": broker_id})
            return broker_id

    def transition(self, key, state, observation):
        with self.transaction() as db:
            row = db.execute("SELECT state FROM outbox WHERE id=?", (key,)).fetchone()
            if not row:
                raise ValueError("Order intent not found.")
            db.execute("UPDATE outbox SET state=? WHERE id=?", (state, key))
            self.append(
                db, "order.observed", {"id": key, "from": row[0], "to": state, **observation}
            )

    def capture(self, observations):
        """Write immutable data before any dependent signal can be committed."""
        import os

        payload = canonical(observations).encode("utf-8")
        identity = digest(observations)
        directory = self.directory / "captures"
        directory.mkdir(exist_ok=True)
        path = directory / f"{identity}.json"
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        elif path.read_bytes() != payload:
            raise Conflict("Captured observations failed their checksum. Recover the data first.")
        return identity

    def load_capture(self, identity):
        import hashlib
        import re

        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise Conflict("Invalid market-data capture identity.")
        with self.connect() as db:
            manifest = db.execute("SELECT * FROM captures WHERE id=?", (identity,)).fetchone()
        if manifest:
            if (
                not re.fullmatch(r"trades-\d{4}-\d{2}-\d{2}\.jsonl", manifest["file"])
                or manifest["offset"] < 0
                or not 0 < manifest["length"] <= 32 * 1024 * 1024
            ):
                raise Conflict("Invalid capture manifest bounds.")
            with (self.directory / "captures" / manifest["file"]).open("rb") as stream:
                stream.seek(manifest["offset"])
                payload = stream.read(manifest["length"])
        else:
            payload = (self.directory / "captures" / f"{identity}.json").read_bytes()
        if hashlib.sha256(payload).hexdigest() != identity:
            raise Conflict("Market-data capture checksum failed. Do not replay this data.")
        return json.loads(payload)

    def capture_batch(self, observations):
        import os

        payload = canonical(observations).encode("utf-8")
        identity = digest(observations)
        directory = self.directory / "captures"
        directory.mkdir(exist_ok=True)
        filename = f"trades-{now()[:10]}.jsonl"
        with self.lock:
            with self.connect() as db:
                if db.execute("SELECT 1 FROM captures WHERE id=?", (identity,)).fetchone():
                    self.load_capture(identity)
                    return identity
            with (directory / filename).open("ab") as stream:
                offset = stream.tell()
                stream.write(payload + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            # Orphan bytes after a crash are never replayed. Only immutable,
            # committed offset/length/checksum manifests can identify a capture.
            with self.transaction() as db:
                db.execute(
                    "INSERT INTO captures VALUES(?,?,?,?)",
                    (identity, filename, offset, len(payload)),
                )
        return identity

    def mark_dispatch(self, key):
        with self.transaction() as db:
            row = db.execute("SELECT payload,run_id FROM outbox WHERE id=?", (key,)).fetchone()
            if row and json.loads(row["payload"]).get("purpose", "entry") == "entry":
                if (self.read(db, "safety", "emergency") or {}).get("active"):
                    raise Conflict("Emergency stop blocks dispatch of this entry.")
                run = self.read(db, "run", row["run_id"])
                reservation = self.read(db, "reservation", key)
                if (
                    not run
                    or run.get("archived")
                    or not run.get("armed")
                    or run.get("expires_at", "") <= now()
                    or not reservation
                    or not reservation.get("active")
                ):
                    raise Conflict(
                        "Entry dispatch requires current authorization and reserved risk."
                    )
            result = db.execute(
                "UPDATE outbox SET state='dispatching' WHERE id=? AND state='reserved'", (key,)
            )
            if result.rowcount != 1:
                raise Conflict("Order cannot be dispatched again. Reconciliation is required.")
            self.append(db, "order.dispatch.started", {"id": key})

    def display_runs(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM documents WHERE kind='run' AND "
                "(json_extract(payload,'$.armed')=1 OR "
                "CAST(json_extract(payload,'$.position') AS REAL)!=0) "
                "UNION SELECT payload FROM (SELECT payload FROM documents WHERE kind='run' "
                "AND COALESCE(json_extract(payload,'$.archived'),0)=0 "
                "ORDER BY rowid DESC LIMIT 50)"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def orders(self, active_only=False):
        with self.connect() as db:
            where = " WHERE state NOT IN ('filled','cancelled','rejected')" if active_only else ""
            rows = db.execute(
                "SELECT * FROM outbox" + where + " ORDER BY created_at DESC"
            ).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def verify(self):
        with self.connect() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Conflict("Database integrity check failed.")
            rows = db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
            for order in db.execute("SELECT hash,payload FROM outbox"):
                if digest(json.loads(order["payload"])) != order["hash"]:
                    raise Conflict("A durable order payload failed its integrity check.")
            for version in db.execute("SELECT payload FROM versions"):
                published = json.loads(version[0])
                if compile_graph(published["document"]).digest != published["hash"]:
                    raise Conflict("A published strategy failed its execution-hash check.")
        previous = "0" * 64
        for row in rows:
            expected = digest([row["timestamp"], row["type"], json.loads(row["payload"]), previous])
            if row["previous_hash"] != previous or row["hash"] != expected:
                raise Conflict("Event chain integrity check failed.")
            previous = expected
        return {"integrity": "ok", "events": len(rows)}

    def backup(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = directory / f"workspace-{stamp}-{uuid.uuid4().hex[:6]}.sqlite3"
        with self.connect() as source, sqlite3.connect(target, factory=Connection) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Conflict("Backup integrity check failed.")
        return target
