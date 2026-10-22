"""Instance-bound, monotonic watchdog health; never grants broker capabilities."""

import json
import math
import os
import time
import uuid


def atomic_health(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        temporary.write_text(json.dumps(value), encoding="utf-8")
        # Windows readers briefly hold a handle without FILE_SHARE_DELETE. Retry the
        # atomic rename, never replace it with a partially visible direct write.
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.01)
    finally:
        temporary.unlink(missing_ok=True)


def read_health(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def fresh_health(value, seconds, wall, monotonic):
    if not isinstance(value, dict):
        return False
    fields = (value.get("timestamp"), value.get("monotonic"))
    return all(type(v) in (int, float) and math.isfinite(v) for v in fields) and (
        value["timestamp"] <= wall and 0 <= monotonic - value["monotonic"] < seconds
    )


def watchdog_status(store, instance=None, *, wall=None, monotonic=None):
    wall = time.time() if wall is None else wall
    monotonic = time.monotonic() if monotonic is None else monotonic
    owner = store.get("workspace", "engine_owner") or {}
    engine = read_health(store.directory / "engine-health.json")
    monitor = read_health(store.directory / "watchdog-health.json")
    detail = "Watchdog is starting; wait for a current engine-matched heartbeat."
    valid_owner = owner.get("instance") and (instance is None or owner["instance"] == instance)
    if not valid_owner or owner.get("state") == "stopped":
        detail = "Watchdog engine ownership is unavailable or has changed. Restart the launcher."
    elif not engine or not monitor:
        detail = "Watchdog heartbeat is missing or malformed. Restart the workspace launcher."
    elif (
        engine.get("instance") != owner["instance"]
        or monitor.get("instance") != owner["instance"]
        or engine.get("pid") != owner.get("pid")
        or monitor.get("engine_pid") != owner.get("pid")
        or type(owner.get("pid")) is not int
        or owner["pid"] <= 0
        or type(monitor.get("pid")) is not int
        or monitor["pid"] <= 0
    ):
        detail = "Watchdog heartbeat belongs to a different engine instance or process."
    elif not fresh_health(engine, 20, wall, monotonic):
        detail = "Watchdog cannot confirm a fresh engine heartbeat (20-second limit)."
    elif not fresh_health(monitor, 15, wall, monotonic):
        detail = "Watchdog heartbeat is stale or future-dated (15-second limit)."
    elif (
        monitor.get("state") != "monitoring"
        or type(engine.get("sequence")) is not int
        or type(monitor.get("engine_sequence")) is not int
        or not 0 < monitor["engine_sequence"] <= engine.get("sequence", 0)
        or not fresh_health(monitor.get("acknowledged", {}), 20, wall, monotonic)
        or monitor["acknowledged"]["monotonic"] > min(engine["monotonic"], monitor["monotonic"])
    ):
        detail = "Watchdog has not acknowledged a fresh heartbeat from this engine."
    else:
        return {
            "ready": True,
            "state": "monitoring",
            "detail": "Independent watchdog acknowledged this engine's fresh heartbeat.",
            "age_seconds": monotonic - monitor["monotonic"],
            "checked_at": monitor["timestamp"],
        }
    return {"ready": False, "state": "unavailable", "detail": detail, "age_seconds": None}
