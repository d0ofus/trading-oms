"""Bounded, non-blocking handling of Windows heartbeat reader sharing locks."""

import json
import os


def publish_health(directory, payload):
    pending = directory / "engine-health.pending"
    pending.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.replace(pending, directory / "engine-health.json")
    except PermissionError:
        return False
    return True
