"""Policy decisions for current dependencies, without broker execution capabilities."""

import os
import time

from .current_conditions import CurrentConditions
from .incidents import CONTRACT_CODES, POLICY_VERSION, SERVICE_RECOVERY
from .store import now


class AutomaticRecovery(CurrentConditions):
    def record_duplicate_incident(self, item):
        summaries = getattr(self, "_duplicate_incident_summaries", {})
        self._duplicate_incident_summaries = summaries
        if item["id"] not in summaries and len(summaries) >= 200:
            summaries.pop(next(iter(summaries)))
        summary = summaries.setdefault(item["id"], {"count": 0, "at": None})
        summary["count"] += 1
        stamp = time.monotonic()
        if summary["at"] is None or stamp - summary["at"] >= 60:
            self.store.event(
                "incident.duplicate_observation",
                {"id": item["id"], "code": item["code"], "count": summary["count"]},
            )
            summary.update(count=0, at=stamp)

    def corrected_fault_recoverable(self, item, db):
        from .fault_policy import corrected_episode
        from .incidents import ACCOUNT_CODES

        return bool(
            self.automatic_recovery_enabled
            and os.environ.get("OMS_DISABLE_CORRECTED_FAULT_RECOVERY") != "1"
            and item["code"] == "engine_fault"
            and self.code_verified
            and corrected_episode(item)
            and not any(
                i["id"] != item["id"]
                and i["code"]
                in (ACCOUNT_CODES | {"order_uncertain", "dispatch_uncertain", "callback_overflow"})
                for i in self.incidents.open(db)
            )
        )

    @property
    def automatic_recovery_enabled(self):
        return os.environ.get("OMS_DISABLE_AUTOMATIC_RECOVERY") != "1"

    def service_incident(self, code, detail, **context):
        # Duplicate callbacks in one uninterrupted service failure are observations,
        # not new failures. A recovery callback or changed connection resets this.
        if code in {*SERVICE_RECOVERY, "broker_2110"}:
            diagnostic = context.get("diagnostic") or {}
            for item in self.incidents.open():
                recovery = getattr(self, "_service_recovery", {}).get(
                    (SERVICE_RECOVERY.get(code), diagnostic.get("farm")), {}
                )
                if (
                    item["code"] == code
                    and item.get("correlation_key", "") == context.get("correlation_key", "")
                    and item["instance"] == self.process_identity
                    and item.get("connection_epoch") == self.broker.epoch
                    and item["condition"] == "active"
                    and not (code == "broker_2110" and item["id"] in self._incident_stability)
                    and recovery.get("sequence", -1) <= item["failure_sequence"]
                ):
                    self.record_duplicate_incident(item)
                    return item
            context["new_failure"] = True  # Recovery or a new context separates service failures.
        return self.incident(code, detail, **context)

    def unused_feed(self, item, db):
        if item["code"] not in CONTRACT_CODES or item["scope"]["type"] != "contract":
            return False
        conid = int(item["scope"]["key"])
        dependencies = self._data_dependencies(db)
        required = [r for r in dependencies["runs"] if r.get("conid") == conid]
        required.extend(self.active_preparations(conid))
        if (
            "history" in item["code"]
            and required
            and all(not self._requires_downloaded_history(r) for r in required)
        ):
            return True  # Only the optional display component is being retired.
        subscription = self.store.read(db, "subscription", str(conid))
        if (subscription or {}).get("active") or conid in self.data:
            return False
        return conid not in dependencies["contracts"]

    def recovery_owner(self, db):
        owner = self.store.read(db, "workspace", "engine_owner") or {}
        return owner.get("instance") == self.process_identity and owner.get("state") != "stopped"

    def automatic_release(self, db, item, evidence, retired=False, corrected=False):
        if not self.recovery_owner(db) or not self.reconciled:
            return
        item.update(
            restriction="released",
            revision=item["revision"] + 1,
            released_at=now(),
            release_actor="automatic-recovery",
            release_policy="automatic",
            policy_version=POLICY_VERSION,
            release_kind="dependency_retired"
            if retired
            else "corrected_data_fault"
            if corrected
            else "verified_recovery",
            release_reason="Restriction retired—dependency no longer used."
            if retired
            else (
                "Corrected data-request fault recovered automatically; "
                "authorization remains revoked."
            )
            if corrected
            else (
                "Current recovery evidence verified automatically; "
                "entry eligibility follows the existing authorization policy."
            ),
            release_evidence=evidence,
        )
        if retired:
            item["condition"] = "unknown"
        item["recovery_detail"] = item["release_reason"]
        self.incidents._save(db, item)
        self.store.append(db, "incident.automatically_released", item)
        from .incidents import clear_notifications

        clear_notifications(self.store, db, item)
        self._overview_cache = None
