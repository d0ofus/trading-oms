"""Versioned, explicitly reviewed entry authorization lifecycle."""

import os

from .store import now

RESUME_POLICY = "same_engine_routine_v1"


def resumable_failure(run, incident, instance):
    if (
        run.get("resume_policy") != RESUME_POLICY
        or run.get("authorization_instance") != instance
        or run.get("expires_at", "") <= now()
        or os.environ.get("OMS_DISABLE_PAPER_RESUME") == "1"
    ):
        return False
    code = incident["code"]
    if code in {"connectivity", "broker_2103", "broker_2105", "broker_2110"}:
        return True
    return code.endswith("_feed_failure") and (incident.get("diagnostic") or {}).get("reason") in {
        "transient",
        "pacing",
    }


class Authorization:
    def resume_authorizations(self):
        if (
            os.environ.get("OMS_DISABLE_PAPER_RESUME") == "1"
            or not self.connected
            or not self.attested
        ):
            return
        for run in self.store.list("run"):
            if run.get("authorization_status") != "temporarily_suspended":
                continue
            if (
                run.get("authorization_instance") != self.process_identity
                or run.get("authorization_context") != getattr(self, "paper_context_token", None)
                or run.get("expires_at", "") <= now()
            ):
                self.disarm(
                    run["id"], "Authorization expired or execution context changed. Review again."
                )
                continue
            if run.get("resume_policy") != RESUME_POLICY or self.incidents.applicable([run]):
                continue
            # An interrupted order must resolve independently. In particular, a
            # terminal zero-fill order never becomes permission to retry the trade.
            if any(
                o["run_id"] == run["id"] and o["created_at"] >= run["authorized_at"]
                for o in self.store.orders()
            ):
                self.disarm(run["id"], "Interrupted order outcome requires a fresh entry review.")
                continue
            preview = self.arm_preview([run["id"]], run["limits"]["id"], run["limits"]["version"])
            if not preview["eligible"]:
                continue
            with self.store.transaction() as db:
                current = self.store.read(db, "run", run["id"])
                if (
                    not current
                    or current.get("authorization_status") != "temporarily_suspended"
                    or not self.recovery_owner(db)
                    or self.incidents.applicable([current], db)
                    or (self.store.read(db, "safety", "emergency") or {}).get("active")
                ):
                    continue
                current.update(
                    armed=True,
                    state="armed",
                    authorization_status="authorized",
                    resumed_at=now(),
                    live_after=now(),
                    blocking_reason=None,
                    epoch=self.broker.epoch,
                )
                self.store.write(db, "run", current["id"], current)
                for namespace in ("stock_trigger", "crypto_trigger"):
                    self.store.write(db, namespace, current["id"], {})
                self.store.append(
                    db,
                    "run.authorization.resumed",
                    {
                        "run_id": current["id"],
                        "authorization_id": current["authorization_id"],
                        "policy": RESUME_POLICY,
                        "entries": current["entries"],
                    },
                )
            self._runtime(current, reset=True)
