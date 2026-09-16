"""Named limits and explicit internal-paper qualification; no live capability."""

from datetime import UTC, datetime, timedelta

from .graph import number
from .store import Conflict, now

DEFAULTS = [
    {
        "id": "smoke",
        "version": 1,
        "name": "Supervised paper smoke test",
        "shares": 1,
        "runs": 1,
        "planned_stop_risk": "10",
        "notional": "1000",
        "daily_loss": "100",
        "entry_timeout": 30,
    },
    {
        "id": "qualified",
        "version": 1,
        "name": "Five-symbol paper qualification",
        "shares": 10,
        "runs": 5,
        "planned_stop_risk": "10",
        "notional": "1000",
        "daily_loss": "100",
        "entry_timeout": 30,
    },
]


def profiles(store):
    for profile in DEFAULTS:
        if store.get("risk_profile", profile["id"] + ":1") is None:
            store.put("risk_profile", profile["id"] + ":1", profile)
    return store.list("risk_profile")


def save_profile(store, profile):
    limits = {
        "shares": 10,
        "runs": 5,
        "planned_stop_risk": 10,
        "notional": 1000,
        "daily_loss": 100,
        "entry_timeout": 30,
    }
    if (
        not set(profile) <= {"id", "name", *limits}
        or not isinstance(profile.get("name"), str)
        or not profile["name"].strip()
        or len(profile["name"]) > 100
    ):
        raise ValueError("Name the profile and use only supported limits.")
    import re

    if (
        not isinstance(profile.get("id"), str)
        or not re.fullmatch(r"[a-z0-9_-]{1,40}", profile["id"])
        or profile["id"]
        in {
            "smoke",
            "qualified",
        }
    ):
        raise ValueError("Choose a new custom profile identity.")
    for field, ceiling in limits.items():
        if not 0 < number(profile.get(field, 0)) <= ceiling:
            raise ValueError(
                f"{field.replace('_', ' ').title()} must be positive and at most {ceiling}."
            )
    for field in ("shares", "runs", "entry_timeout"):
        if type(profile[field]) is not int:
            raise ValueError("Share, run and timeout limits require whole numbers.")
    profiles(store)
    with store.transaction() as db:
        current = [p for p in store.list("risk_profile") if p["id"] == profile["id"]]
        record = {**profile, "version": max((p["version"] for p in current), default=0) + 1}
        store.write(db, "risk_profile", f"{record['id']}:{record['version']}", record)
        store.append(db, "risk_profile.published", record)
    return record


def qualification_checks(store, profile, unattended, code_verified):
    evidence = store.get("qualification", "broker_evidence") or {}
    review = store.get("qualification", "operator_review") or {}
    checks = [
        {
            "code": "verified_build",
            "title": "Verified application build",
            "passed": code_verified,
            "detail": "Run this build's verification gate and complete its recorded safety review.",
            "remediation": "/settings",
        }
    ]
    if profile["shares"] > 1 or profile["runs"] > 1:
        checks.append(
            {
                "code": "supervised_qualification",
                "title": "Supervised expansion accepted",
                "passed": bool(evidence.get("smoke_completed") and review.get("supervised")),
                "detail": "Complete a one-share entry, verify protection, close and reconcile. "
                "Then accept supervised expansion.",
                "remediation": "/settings",
            }
        )
    if unattended:
        recent = datetime.now(UTC) - timedelta(hours=24)
        notifications = all(
            (store.get("monitoring", channel) or {}).get("tested")
            and datetime.fromisoformat(store.get("monitoring", channel)["timestamp"]) > recent
            for channel in ("telegram", "healthchecks")
        )
        watchdog = store.directory / "watchdog-health.json"
        import time

        heartbeat = store.get("monitoring", "last_heartbeat") or {}
        heartbeat_ready = heartbeat.get("passed") and datetime.fromisoformat(
            heartbeat.get("timestamp", "2000-01-01T00:00:00+00:00")
        ) > datetime.now(UTC) - timedelta(seconds=90)

        checks.extend(
            [
                {
                    "code": "unattended_acceptance",
                    "title": "Unattended paper trial accepted",
                    "passed": bool(
                        review.get("unattended")
                        and evidence.get("temporary_recovery")
                        and evidence.get("smoke_completed")
                        and (profile["shares"] == 1 or evidence.get("partial_repair_verified"))
                    ),
                    "detail": "Complete supervised execution and recovery trials. "
                    "Multi-share sessions also require observed partial-fill repair. "
                    "Accept the configuration walkthrough and outage test.",
                    "remediation": "/settings",
                },
                {
                    "code": "notification_tests",
                    "title": "Notification tests passed today",
                    "passed": notifications and bool(heartbeat_ready),
                    "detail": "Test Telegram and Healthchecks. "
                    "Use a one-minute period and two-minute grace period.",
                    "remediation": "/settings",
                },
                {
                    "code": "watchdog",
                    "title": "Independent watchdog running",
                    "passed": watchdog.exists() and time.time() - watchdog.stat().st_mtime < 15,
                    "detail": "Start the packaged local launcher with its independent watchdog.",
                    "remediation": "/settings",
                },
                {
                    "code": "restore_test",
                    "title": "Backup restore validated",
                    "passed": bool(store.get("qualification", "restore_test")),
                    "detail": "Create a backup and validate a restore in a separate directory.",
                    "remediation": "/settings",
                },
            ]
        )
    return checks


def accept_review(store, stage, confirmed):
    if confirmed is not True or stage not in {"supervised", "unattended"}:
        raise ValueError("Review and explicitly accept the selected internal paper stage.")
    evidence = store.get("qualification", "broker_evidence") or {}
    if not evidence.get("smoke_completed"):
        raise Conflict("A reconciled one-share paper execution and close are required first.")
    if stage == "unattended" and not evidence.get("temporary_recovery"):
        raise Conflict(
            "Demonstrate temporary connection recovery in a supervised paper session first."
        )
    review = store.get("qualification", "operator_review") or {}
    review.update({stage: True, stage + "_accepted_at": now()})
    store.put("qualification", "operator_review", review)
    store.event(
        "qualification.operator_accepted", {"stage": stage, "independent_review_claimed": False}
    )
    return review
