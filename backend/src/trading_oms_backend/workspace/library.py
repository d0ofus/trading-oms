"""Audited library lifecycle; immutable execution definitions are never deleted."""

import json
import uuid
from datetime import UTC, datetime

from .graph import digest
from .store import Conflict, now


def require_available(store, db, key):
    record = store.read(db, "strategy_lifecycle", key) or {}
    if record.get("state") in {"archived", "deleted"}:
        raise Conflict("Strategy was removed from the library. Restore an archived strategy first.")


class StrategyLibrary:
    def __init__(self, store):
        self.store = store

    def listing(self, archived=False):
        with self.store.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT d.payload FROM documents d LEFT JOIN documents l "
                    "ON l.kind='strategy_lifecycle' AND l.id=d.id WHERE d.kind='draft' "
                    "AND COALESCE(json_extract(l.payload,'$.state'),'active')=? "
                    "ORDER BY d.rowid DESC",
                    ("archived" if archived else "active",),
                )
            ]

    def _item(self, db, key):
        d = self.store.read(db, "draft", key)
        if not d:
            raise Conflict("A selected strategy no longer exists. Refresh the library.")
        require_available(self.store, db, key)
        references = db.execute(
            "SELECT DISTINCT d.kind,d.id FROM documents d,json_tree(d.payload) j "
            "WHERE d.kind NOT IN ('draft','strategy_lifecycle','library_preview',"
            "'library_receipt','http_mutation','preferences') "
            "AND j.type='text' AND j.value=? ORDER BY d.kind,d.id",
            (key,),
        ).fetchall()
        published = bool(
            db.execute("SELECT 1 FROM versions WHERE strategy_id=? LIMIT 1", (key,)).fetchone()
        )
        runs = [
            self.store.read(db, kind, identity) for kind, identity in references if kind == "run"
        ]
        return {
            "id": key,
            "name": d["name"],
            "revision": d["revision"],
            "action": "archive" if published or references else "delete",
            "runs": [
                {k: r.get(k) for k in ("id", "name", "armed", "position", "state")} for r in runs
            ],
            "fingerprint": digest(
                {"draft": d, "published": published, "references": [list(r) for r in references]}
            ),
        }

    def preview(self, ids):
        if not 1 <= len(ids) <= 50 or len(set(ids)) != len(ids):
            raise ValueError("Select one to fifty distinct strategies.")
        with self.store.transaction() as db:
            p = {
                "preview_id": uuid.uuid4().hex,
                "created_at": now(),
                "items": [self._item(db, key) for key in ids],
            }
            self.store.write(db, "library_preview", p["preview_id"], p)
            db.execute(
                "DELETE FROM documents WHERE kind='library_preview' AND rowid NOT IN "
                "(SELECT rowid FROM documents WHERE kind='library_preview' "
                "ORDER BY rowid DESC LIMIT 20)"
            )
        return p

    def confirm(self, preview_id, mutation_id, actor):
        self.store.backup(self.store.directory / "backups")
        with self.store.transaction() as db:
            prior = self.store.read(db, "library_receipt", mutation_id)
            if prior:
                if prior["preview_id"] != preview_id or prior["actor"] != actor:
                    raise Conflict("Action identifier already used for another removal.")
                return prior["result"]
            p = self.store.read(db, "library_preview", preview_id)
            if (
                not p
                or not 0
                <= (datetime.now(UTC) - datetime.fromisoformat(p["created_at"])).total_seconds()
                <= 300
            ):
                raise Conflict("Library review expired. Review removal again.")
            items = [self._item(db, item["id"]) for item in p["items"]]
            if any(
                a["fingerprint"] != b["fingerprint"] for a, b in zip(items, p["items"], strict=True)
            ):
                raise Conflict("A strategy or its references changed. Review removal again.")
            result = {"deleted": [], "archived": []}
            for item in items:
                state = "deleted" if item["action"] == "delete" else "archived"
                record = {
                    "state": state,
                    "at": now(),
                    "actor": actor,
                    "revision": item["revision"],
                    "mutation_id": mutation_id,
                }
                self.store.write(db, "strategy_lifecycle", item["id"], record)
                if state == "deleted":
                    db.execute("DELETE FROM documents WHERE kind='draft' AND id=?", (item["id"],))
                    # Mutation response caches are not durable strategy usage. Remove
                    # saved draft bodies so replay cannot return a deleted draft.
                    cached = db.execute(
                        "SELECT DISTINCT d.id FROM documents d,json_tree(d.payload) j "
                        "WHERE d.kind='http_mutation' AND j.type='text' AND j.value=?",
                        (item["id"],),
                    ).fetchall()
                    for row in cached:
                        old = self.store.read(db, "http_mutation", row[0])
                        self.store.write(
                            db,
                            "http_mutation",
                            row[0],
                            {
                                **old,
                                "status": 409,
                                "response": {
                                    "detail": "This strategy was deleted from the library."
                                },
                            },
                        )
                self.store.append(
                    db, "strategy.library." + state, {"strategy_id": item["id"], **record}
                )
                result[state].append(item["id"])
            self.store.write(
                db,
                "library_receipt",
                mutation_id,
                {"preview_id": preview_id, "actor": actor, "result": result},
            )
        return result

    def restore(self, key, actor):
        with self.store.transaction() as db:
            old = self.store.read(db, "strategy_lifecycle", key) or {}
            if old.get("state") != "archived":
                raise Conflict("Only an archived strategy can be restored.")
            self.store.write(
                db,
                "strategy_lifecycle",
                key,
                {**old, "state": "active", "restored_at": now(), "actor": actor},
            )
            self.store.append(db, "strategy.library.restored", {"strategy_id": key, "actor": actor})
        return {"restored": key}
