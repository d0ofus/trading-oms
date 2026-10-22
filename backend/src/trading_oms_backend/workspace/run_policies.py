"""Nonexecuting adoption of current policies; historical bindings stay immutable."""

import os

from .credit_policy import CURRENT_POLICY as POLICY
from .credit_policy import QUIET_POLICY, ensure_policy
from .fx_policy import BROKER_CANDLES
from .graph import digest, number
from .library import require_available
from .store import Conflict, now

INSTALLATION = "inline_policy_replacement_v1"
RESTORATION = "inline_policy_restoration_v1"


def identity(contract):
    return {
        **{
            k: contract.get(k)
            for k in (
                "conid",
                "symbol",
                "sec_type",
                "currency",
                "primary_exchange",
                "trading_class",
                "local_symbol",
                "multiplier",
            )
        },
        "route": contract.get("routing_exchange") or contract.get("exchange"),
    }


def current_policy(run):
    plan = (run.get("binding") or {}).get("execution_plan") or {}
    return plan.get("funding_policy") == POLICY and (
        plan.get("family") != "spot_fx"
        or (
            plan.get("authorization_policy") == QUIET_POLICY
            and plan.get("policy") == BROKER_CANDLES
        )
    )


def replacement_key(run):
    return ":".join((run["id"], run["binding"]["hash"], POLICY)) + (
        ":" + BROKER_CANDLES
        if run["binding"].get("execution_plan", {}).get("family") == "spot_fx"
        else ""
    )


class RunPolicies:
    def _replacement_blockers(self, db, run, allow_archived=False):
        reasons = self._archive_item(db, run["id"])["reasons"]
        if run.get("archived") and not allow_archived:
            reasons.append("Archived runs cannot be replaced from authorization review.")
        if run.get("authorization_status") in {"authorized", "temporarily_suspended"}:
            reasons.append("Disarm the existing authorization before replacing its policy.")
        for kind in ("fx_protection", "stock_protection", "crypto_protection"):
            operation = self.store.read(db, kind, run["id"])
            if operation and operation.get("state") not in {"closed", "completed"}:
                reasons.append("An outstanding protection operation requires reconciliation.")
        if number(self.owned().get(run["id"], {}).get("quantity", 0)):
            reasons.append("Confirmed executions still establish owned exposure.")
        return list(dict.fromkeys(reasons))

    def _replacement_target_blockers(self, db, target, source):
        reasons = self._replacement_blockers(db, target, allow_archived=True)
        binding = target.get("binding") or {}
        if (
            not current_policy(target)
            or binding.get("hash") != digest({k: v for k, v in binding.items() if k != "hash"})
            or any(
                target.get(k) != source.get(k)
                for k in ("strategy_id", "version", "conid", "protection_type")
            )
            or binding.get("sizing") != source["binding"]["sizing"]
        ):
            reasons.append(
                "The existing replacement binding or settings changed. Review preparation."
            )
        if (
            target.get("entries")
            or db.execute("SELECT 1 FROM outbox WHERE run_id=?", (target["id"],)).fetchone()
        ):
            reasons.append(
                "The existing replacement has broker activity; inspect it and prepare a new run."
            )
        return reasons

    def _replacement_candidate(self, run):
        binding = run.get("binding") or {}
        plan = binding.get("execution_plan") or {}
        if binding.get("hash") != digest({k: v for k, v in binding.items() if k != "hash"}):
            raise Conflict("Source binding changed. Review preparation.")
        if not plan or self.store.version(run["strategy_id"], run["version"])["document"][
            "schema_version"
        ] not in {7, 8, 9}:
            raise Conflict(
                "This strategy requires explicit conversion before current-policy preparation."
            )
        if identity(binding["contract"]) != identity(self.contracts.get(run["conid"], {})):
            raise Conflict("Contract identity or route changed. Review the prefilled preparation.")
        session = "fx" if self._fx_run(run) else plan.get("session_mode", "regular")
        compatible = self.stock_compatibility(
            run["strategy_id"],
            run["version"],
            run["conid"],
            plan["protection_type"],
            session,
            binding["sizing"],
            POLICY,
            BROKER_CANDLES if self._fx_run(run) else None,
        )
        if not compatible.get("can_prepare", not compatible["blockers"]) or not compatible.get(
            "plan"
        ):
            raise Conflict(
                " ".join(compatible.get("preparation_blockers") or compatible["blockers"])
            )
        candidate = self._build_run(
            run["strategy_id"],
            run["version"],
            run["conid"],
            binding["sizing"],
            plan["protection_type"],
            compatible["plan"]["hash"],
            session,
            POLICY,
            BROKER_CANDLES if self._fx_run(run) else None,
        )
        if (
            candidate["binding"]["sizing"] != binding["sizing"]
            or candidate["binding"]["strategy_hash"] != binding["strategy_hash"]
        ):
            raise Conflict(
                "Published strategy or exact sizing changed. Review the prefilled preparation."
            )
        return candidate

    def policy_replacement_preview(self, runs):
        items = []
        disabled = (
            os.environ.get("OMS_DISABLE_POLICY_REPLACEMENT") == "1"
            or os.environ.get("OMS_DISABLE_PAPER_BUYING_POWER_ARM") == "1"
        )
        for run in runs:
            if not (run.get("binding") or {}).get("execution_plan"):
                continue
            needed = not current_policy(run)
            item = {
                "run_id": run["id"],
                "binding_hash": run["binding"]["hash"],
                "needs_replacement": needed,
                "blockers": [],
                "replacement_id": None,
                "replacement_state": None,
                "action": "adopt",
            }
            if needed:
                with self.store.connect() as db:
                    item["blockers"] = self._replacement_blockers(db, run)
                    link = self.store.read(db, "policy_replacement", replacement_key(run))
                    if link:
                        item["replacement_id"] = link["replacement_id"]
                        target = self.store.read(db, "run", link["replacement_id"])
                        if (
                            link["source_binding_hash"] != run["binding"]["hash"]
                            or not target
                            or target["binding"]["hash"] != link["target_binding_hash"]
                        ):
                            item["blockers"].append(
                                "The existing replacement changed; review its preparation."
                            )
                        else:
                            item["replacement_state"] = digest(target)
                            item["action"] = "restore" if target.get("archived") else "adopt"
                            item["blockers"].extend(
                                "Existing replacement: " + reason
                                for reason in self._replacement_target_blockers(db, target, run)
                            )
                if disabled:
                    item["blockers"].append(
                        "Current-policy replacement is disabled by the execution host."
                    )
                if not item["blockers"]:
                    try:
                        candidate = self._replacement_candidate(run)
                        if (
                            link
                            and target["binding"]["execution_plan"]["hash"]
                            != candidate["binding"]["execution_plan"]["hash"]
                        ):
                            item["blockers"].append(
                                "The linked replacement no longer matches current contract "
                                "requirements. Review preparation."
                            )
                    except (ValueError, KeyError) as exc:
                        item["blockers"].append(str(exc))
            items.append(item)
        needed = [i for i in items if i["needs_replacement"]]
        return {
            "target_policy_revision": POLICY,
            "target_execution_policy_revision": BROKER_CANDLES,
            "items": items,
            "eligible": bool(needed) and not any(i["blockers"] for i in needed),
        }

    def policy_replacement(
        self,
        ids,
        expected_binding_hashes,
        target_policy_revision,
        mutation_id,
        actor,
        action="adopt",
        expected_replacement_states=None,
        target_execution_policy_revision=None,
    ):
        if target_execution_policy_revision not in {None, BROKER_CANDLES}:
            raise Conflict("The FX execution policy changed. Refresh review.")
        if (
            not 1 <= len(ids) <= 5
            or len(ids) != len(set(ids))
            or set(ids) != set(expected_binding_hashes)
        ):
            raise Conflict("Select one to five distinct runs with their reviewed binding hashes.")
        if target_policy_revision != POLICY:
            raise Conflict("The target execution policy changed. Refresh the review.")
        if (
            self.environment.crypto
            or os.environ.get("OMS_DISABLE_POLICY_REPLACEMENT") == "1"
            or os.environ.get("OMS_DISABLE_PAPER_BUYING_POWER_ARM") == "1"
        ):
            raise Conflict(
                "Current-policy replacement is unavailable in this execution environment."
            )
        expected_replacement_states = expected_replacement_states or {}
        if action not in {"adopt", "restore"} or len(expected_replacement_states) > 5:
            raise Conflict("Choose an explicit current-policy adoption or restoration action.")
        request = {
            "ids": ids,
            "hashes": expected_binding_hashes,
            "policy": target_policy_revision,
            "actor": actor,
        }
        # Keep legacy creation receipt fingerprints stable. Restoration always has new intent.
        if action != "adopt" or expected_replacement_states:
            request.update(action=action, replacement_states=expected_replacement_states)
        if target_execution_policy_revision:
            request["execution_policy"] = target_execution_policy_revision
        signature = digest(request)
        # The execution owner serializes commands; this lock also protects direct callers.
        with self.store.lock:
            receipt = self.store.get("policy_replacement_receipt", mutation_id)
            if receipt:
                if receipt["request_hash"] != signature:
                    raise Conflict("Action identifier was already used for another replacement.")
                return receipt["result"]
            runs = [self.store.get("run", key) for key in ids]
            if any(
                not r or (r.get("binding") or {}).get("hash") != expected_binding_hashes[r["id"]]
                for r in runs
            ):
                raise Conflict("Source run or binding changed. Refresh the review.")
            preview = self.policy_replacement_preview(runs)
            if not preview["eligible"]:
                raise Conflict(
                    " ".join(b for i in preview["items"] for b in i["blockers"])
                    or "Selected runs already use the current policy."
                )
            restores = {
                i["replacement_id"]: i["replacement_state"]
                for i in preview["items"]
                if i["action"] == "restore"
            }
            if restores and (action != "restore" or expected_replacement_states != restores):
                raise Conflict(
                    "Explicit restoration with the current replacement state is required. "
                    "Refresh review."
                )
            if action == "restore" and not restores:
                raise Conflict("The replacement restoration state changed. Refresh review.")
            candidates = {
                r["id"]: self._replacement_candidate(r) for r in runs if not current_policy(r)
            }
            # Backup/install occurs outside the atomic source/target transaction.
            ensure_policy(self.store, POLICY)
            installation = RESTORATION if restores else INSTALLATION
            if not self.store.get("policy_installation", installation):
                self.store.backup(self.store.directory / "backups")
            created, replacements, review_ids = [], [], []
            with self.store.transaction() as db:
                owner = self.store.read(db, "workspace", "engine_owner") or {}
                if (
                    owner.get("instance") != self.process_identity
                    or owner.get("state") == "stopped"
                ):
                    raise Conflict("The execution owner changed. Refresh the review.")
                for original in runs:
                    source = self.store.read(db, "run", original["id"])
                    if (
                        not source
                        or source["binding"]["hash"] != expected_binding_hashes[source["id"]]
                    ):
                        raise Conflict("Source binding changed. Refresh the review.")
                    if current_policy(source):
                        review_ids.append(source["id"])
                        continue
                    reasons = self._replacement_blockers(db, source)
                    if reasons:
                        raise Conflict(" ".join(reasons))
                    require_available(self.store, db, source["strategy_id"])
                    key = replacement_key(source)
                    link = self.store.read(db, "policy_replacement", key)
                    candidate = candidates[source["id"]]
                    if link:
                        target = self.store.read(db, "run", link["replacement_id"])
                        if (
                            link["source_binding_hash"] != source["binding"]["hash"]
                            or not target
                            or target["binding"]["hash"] != link["target_binding_hash"]
                            or target["binding"]["execution_plan"]["hash"]
                            != candidate["binding"]["execution_plan"]["hash"]
                            or self._replacement_target_blockers(db, target, source)
                        ):
                            raise Conflict(
                                "The existing replacement changed or has been used. "
                                "Inspect that run."
                            )
                        if target.get("archived"):
                            if action != "restore" or expected_replacement_states.get(
                                target["id"]
                            ) != digest(target):
                                raise Conflict(
                                    "The replacement restoration state changed. Refresh review."
                                )
                            restoration = {
                                "at": now(),
                                "actor": actor,
                                "instance": self.process_identity,
                                "mutation_id": mutation_id,
                                "source_id": source["id"],
                            }
                            target.update(archived=False, restoration=restoration)
                            self.store.write(db, "run", target["id"], target)
                            self.store.append(
                                db,
                                "run.policy_replacement.restored",
                                {"run_id": target["id"], **restoration},
                            )
                            created.append(target)
                        elif target["id"] in expected_replacement_states:
                            raise Conflict(
                                "The replacement was already restored or changed. Refresh review."
                            )
                    else:
                        target = candidate
                        self.store.write(db, "run", target["id"], target)
                        link = {
                            "source_id": source["id"],
                            "replacement_id": target["id"],
                            "source_binding_hash": source["binding"]["hash"],
                            "target_binding_hash": target["binding"]["hash"],
                            "policy": POLICY,
                            "actor": actor,
                            "created_at": now(),
                        }
                        self.store.write(db, "policy_replacement", key, link)
                        self.store.append(db, "run.policy_replaced", link)
                        self.store.append(
                            db,
                            "run.created",
                            {
                                "run_id": target["id"],
                                "strategy_id": target["strategy_id"],
                                "version": target["version"],
                            },
                        )
                        created.append(target)
                    replacements.append(link)
                    review_ids.append(target["id"])
                result = {"replacements": replacements, "review_ids": review_ids}
                self.store.write(db, "policy_installation", installation, {"at": now()})
                self.store.write(
                    db,
                    "policy_replacement_receipt",
                    mutation_id,
                    {"request_hash": signature, "result": result},
                )
                self.store.append(
                    db,
                    "run.policy_replacement.confirmed",
                    {
                        "actor": actor,
                        "mutation_id": mutation_id,
                        "review_ids": review_ids,
                        "action": action,
                    },
                )
            self._overview_cache = None
            for run in created:
                self._prepare_run_data(run)
            return result
