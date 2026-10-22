"""Reversible presentation archival; broker ownership is never discarded."""

import json
import time
import uuid
from decimal import Decimal

from .dependencies import never_submitted, operation_active
from .graph import digest
from .order_status import project_status
from .protection import TERMINAL, order_ids
from .store import Conflict, now


class RunArchive:
    def _archive_item(self, db, key):
        run = self.store.read(db, "run", key)
        if not run:
            return {"id": key, "name": key, "reasons": ["Run no longer exists."]}
        reasons = []
        reasons.extend(
            d["detail"]
            for d in self._data_dependencies(db)["reasons"].get(run.get("conid"), [])
            if d.get("run_id") == key
        )
        if db.execute(
            "SELECT 1 FROM documents WHERE kind='reservation' "
            "AND json_extract(payload,'$.run_id')=? AND json_extract(payload,'$.active')=1",
            (key,),
        ).fetchone():
            reasons.append("An active risk reservation remains.")
        if run.get("armed"):
            reasons.append("Disarm the run first.")
        if Decimal(str(run.get("position", 0))) != 0:
            reasons.append("The run has an owned position.")
        rows = db.execute("SELECT * FROM outbox WHERE run_id=?", (key,)).fetchall()
        orders = [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]
        orders = [o for o in orders if not never_submitted(db, o)]
        for order in orders:
            if order["state"] not in {"filled", "cancelled", "rejected"}:
                reasons.append("An order is working, cancelling or unresolved.")
            if (self.store.read(db, "reservation", order["id"]) or {}).get("active"):
                reasons.append("An active risk reservation remains.")
            for broker_id in order_ids(order):
                observed = self.store.read(db, "broker_order", str(broker_id)) or {}
                if observed.get("status") not in TERMINAL or observed.get("status_conflict"):
                    reasons.append(
                        "An entry, exit or protective leg lacks a confirmed terminal state."
                    )
                cancellation = self.store.read(db, "cancel_request", str(broker_id)) or {}
                if cancellation and cancellation.get("state") != "confirmed":
                    reasons.append("Cancellation confirmation is outstanding.")
        if operation_active("exit_request", self.store.read(db, "exit_request", key)):
            reasons.append("An exit operation is outstanding.")
        if operation_active("incident_cancel", self.store.read(db, "incident_cancel", key)):
            reasons.append("Incident cancellation processing is outstanding.")
        # Local projections alone cannot establish flatness after a broker submission.
        if orders:
            proof = self.reconciliation_evidence or {}
            if not (
                self.connected
                and self.attested
                and self.broker.paper_context
                and self.reconciled
                and 0 <= time.monotonic() - self.reconciled_at < 30
                and proof.get("ready")
                and proof.get("instance") == self.process_identity
                and proof.get("epoch") == self.broker.epoch
            ):
                reasons.append(
                    "Broker activity requires fresh successful reconciliation in this session."
                )
            if Decimal(str(self.owned().get(key, {}).get("quantity", 0))) != 0:
                reasons.append("Confirmed executions still establish owned exposure.")
        return {
            "id": key,
            "name": run.get("name", key),
            "archived": bool(run.get("archived")),
            "reasons": list(dict.fromkeys(reasons)),
            "fingerprint": digest(run),
        }

    def archive_preview(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or len(set(ids)) != len(ids):
            raise ValueError("Select one to fifty distinct runs.")
        with self.store.transaction() as db:
            items = [self._archive_item(db, key) for key in ids]
            result = {
                "preview_id": uuid.uuid4().hex,
                "instance": self.process_identity,
                "items": items,
                "eligible": all(not i["reasons"] for i in items),
            }
            self.store.write(db, "archive_preview", result["preview_id"], result)
            # Previews are disposable; confirmations are durable audit receipts.
            db.execute(
                "DELETE FROM documents WHERE kind='archive_preview' AND rowid NOT IN "
                "(SELECT rowid FROM documents WHERE kind='archive_preview' "
                "ORDER BY rowid DESC LIMIT 20)"
            )
        return result

    def archive_confirm(self, preview_id, mutation_id, actor):
        with self.store.transaction() as db:
            prior = self.store.read(db, "archive_receipt", mutation_id)
            if prior:
                if prior["preview_id"] != preview_id or prior["actor"] != actor:
                    raise Conflict("Action identifier already used for another archive request.")
                return prior["result"]
            preview = self.store.read(db, "archive_preview", preview_id)
            owner = self.store.read(db, "workspace", "engine_owner") or {}
            if (
                not preview
                or preview["instance"] != self.process_identity
                or owner.get("instance") != self.process_identity
                or owner.get("state") == "stopped"
            ):
                raise Conflict("Archive review expired or engine changed. Review again.")
            items = [self._archive_item(db, i["id"]) for i in preview["items"]]
            for item, reviewed in zip(items, preview["items"], strict=True):
                if item["reasons"]:
                    raise Conflict(item["name"] + ": " + " ".join(item["reasons"]))
                if item["fingerprint"] != reviewed["fingerprint"]:
                    raise Conflict(
                        item["name"] + ": run changed. Review archive eligibility again."
                    )
            for item in items:
                run = self.store.read(db, "run", item["id"])
                if run.get("archived"):
                    continue
                run.update(
                    archived=True,
                    archive={
                        "at": now(),
                        "actor": actor,
                        "instance": self.process_identity,
                        "mutation_id": mutation_id,
                    },
                )
                self.store.write(db, "run", run["id"], run)
                self.store.append(db, "run.archived", {"run_id": run["id"], **run["archive"]})
            result = {"archived": [i["id"] for i in items]}
            self.store.write(
                db,
                "archive_receipt",
                mutation_id,
                {"preview_id": preview_id, "actor": actor, "result": result},
            )
        self._overview_cache = None
        self._retire_data_jobs()
        return result

    def restore_archived_observation(self, event):
        """Only new/conflicting authoritative activity restores visibility, not replayed history."""
        if event.get("client_id", self.broker.client_id) != self.broker.client_id:
            return
        kind = event["type"]
        if kind == "position" and event.get("own_account"):
            expected = sum(
                (
                    Decimal(str(p["quantity"]))
                    for p in self.owned().values()
                    if p["conid"] == event["conid"]
                ),
                Decimal(0),
            )
            if Decimal(str(event["quantity"])) == expected:
                return
            with self.store.transaction() as db:
                for row in db.execute(
                    "SELECT payload FROM documents WHERE kind='run' "
                    "AND json_extract(payload,'$.archived')=1 "
                    "AND json_extract(payload,'$.conid')=?",
                    (event["conid"],),
                ).fetchall():
                    run = json.loads(row[0])
                    run.update(
                        archived=False,
                        armed=False,
                        state="paused",
                        blocking_reason=(
                            "Unexplained broker position after archival. Reconcile ownership."
                        ),
                    )
                    self.store.write(db, "run", run["id"], run)
                    self.store.append(
                        db, "run.archive.recovery", {"run_id": run["id"], "observation": kind}
                    )
                    self.incidents.raise_in(
                        db, "archived_run_activity", run["blocking_reason"], self.process_identity
                    )
                    self.reconciled = False
                    self._overview_cache = None
            return
        if kind not in {"execution", "open_order", "order_status"}:
            return
        with self.store.transaction() as db:
            if kind == "execution":
                old = db.execute(
                    "SELECT payload FROM executions WHERE id=?", (event["execution_id"],)
                ).fetchone()
                if old and json.loads(old[0]) == {
                    k: v for k, v in event.items() if k not in {"epoch", "sequence"}
                }:
                    return
            if kind != "execution":
                prior = self.store.read(db, "broker_order", str(event["broker_id"])) or {}
                _, disposition = project_status(prior, event)
                identity_changed = (
                    prior.get("permanent_id")
                    and event.get("permanent_id")
                    and prior["permanent_id"] != event["permanent_id"]
                )
                if (
                    disposition in {"late_pending", "late_terminal", "late_rejection"}
                    and not identity_changed
                ):
                    return
                if (
                    event.get("status") in TERMINAL
                    and prior.get("status") == event.get("status")
                    and all(
                        event.get(k, prior.get(k)) == prior.get(k)
                        for k in ("filled", "remaining", "permanent_id")
                    )
                ):
                    return
            orders = [
                {**dict(r), "payload": json.loads(r["payload"])}
                for r in db.execute("SELECT * FROM outbox")
            ]
            for order in orders:
                if event["broker_id"] not in order_ids(order):
                    continue
                run = self.store.read(db, "run", order["run_id"])
                if not run or not run.get("archived"):
                    continue
                run.update(
                    archived=False,
                    armed=False,
                    state="paused",
                    blocking_reason=(
                        "Broker activity after archival. Reconcile ownership and protection."
                    ),
                )
                self.store.write(db, "run", run["id"], run)
                self.store.append(
                    db,
                    "run.archive.recovery",
                    {"run_id": run["id"], "broker_id": event["broker_id"], "observation": kind},
                )
                self.incidents.raise_in(
                    db, "archived_run_activity", run["blocking_reason"], self.process_identity
                )
                self.reconciled = False
                self._overview_cache = None
