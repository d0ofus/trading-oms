"""Windows-only secret storage and sanitized outbound monitoring."""

from __future__ import annotations

import ctypes
import logging
import os
import re
import threading
import time
from ctypes import wintypes
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from .recovery import backup_bundle
from .store import Store, now


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class Vault:
    def __init__(self, namespace="TradingOMS/paper"):
        self.namespace = namespace

    def _api(self):
        if os.name != "nt":
            raise ValueError("Monitoring credentials require Windows Credential Manager.")
        library = ctypes.WinDLL("advapi32", use_last_error=True)
        library.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(Credential)),
        ]
        library.CredReadW.restype = wintypes.BOOL
        library.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        library.CredWriteW.restype = wintypes.BOOL
        library.CredFree.argtypes = [ctypes.c_void_p]
        return library

    def read(self, key):
        api = self._api()
        value = ctypes.POINTER(Credential)()
        if not api.CredReadW(f"{self.namespace}/{key}", 1, 0, ctypes.byref(value)):
            if ctypes.get_last_error() == 1168:
                return None
            raise ValueError(
                "Windows Credential Manager could not read the monitoring configuration."
            )
        try:
            return ctypes.string_at(
                value.contents.CredentialBlob, value.contents.CredentialBlobSize
            ).decode("utf-8")
        finally:
            api.CredFree(value)

    def write(self, key, secret):
        raw = secret.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        credential = Credential()
        credential.Type, credential.Persist = 1, 2
        credential.TargetName = f"{self.namespace}/{key}"
        credential.UserName = "TradingOMS local operator"
        credential.CredentialBlobSize, credential.CredentialBlob = len(raw), buffer
        try:
            if not self._api().CredWriteW(ctypes.byref(credential), 0):
                raise ValueError("Windows Credential Manager could not save the configuration.")
        finally:
            ctypes.memset(buffer, 0, len(raw))


def validate_configuration(token, destination, heartbeat):
    if not re.fullmatch(r"[0-9]{5,15}:[A-Za-z0-9_-]{20,100}", token):
        raise ValueError("Enter a valid Telegram bot token.")
    if not re.fullmatch(r"-?[0-9]{1,20}", destination):
        raise ValueError("Enter the numeric Telegram destination.")
    parsed = urlparse(heartbeat)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "hc-ping.com"
        or not re.fullmatch(r"/[a-f0-9-]{36}", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use the HTTPS Healthchecks ping URL without query parameters.")


class Monitoring:
    def __init__(self, store: Store, healthy, *, vault=None, transport=None):
        self.store, self.healthy = store, healthy
        self.vault = vault or Vault()
        self.transport = transport
        self.stop_event = threading.Event()
        self.thread = None
        self.next_heartbeat = 0.0
        self.last_backup_day = None
        # Never log URLs containing notification credentials, even if a caller
        # raises the root logging level for another subsystem.
        for name in ("httpx", "httpcore"):
            logger = logging.getLogger(name)
            logger.handlers = [logging.NullHandler()]
            logger.propagate = False

    def status(self):
        try:
            configured = all(
                self.vault.read(key)
                for key in ("telegram_token", "telegram_chat", "healthchecks_url")
            )
        except ValueError:
            configured = False
        return {
            "configured": configured,
            "telegram": self.store.get("monitoring", "telegram"),
            "healthchecks": self.store.get("monitoring", "healthchecks"),
            "pending": sum(n.get("state") == "queued" for n in self.store.list("notification")),
            "heartbeat_seconds": 30,
        }

    def configure(self, token, destination, heartbeat):
        validate_configuration(token, destination, heartbeat)
        for key, value in [
            ("telegram_token", token),
            ("telegram_chat", destination),
            ("healthchecks_url", heartbeat),
        ]:
            self.vault.write(key, value)
        self.store.event("monitoring.configured", {"storage": "windows_credential_manager"})
        # Changed credentials invalidate previous successful tests.
        self.store.put("monitoring", "telegram", {"tested": False})
        self.store.put("monitoring", "healthchecks", {"tested": False})
        return {"configured": True}

    def deliver(
        self, channel, text="Trading OMS paper workspace: operator-requested notification test."
    ):
        token, destination, heartbeat = (
            self.vault.read(k) for k in ("telegram_token", "telegram_chat", "healthchecks_url")
        )
        if not token or not destination or not heartbeat:
            raise ValueError("Configure monitoring credentials before sending a test.")
        validate_configuration(token, destination, heartbeat)
        with httpx.Client(
            timeout=8, follow_redirects=False, transport=self.transport, trust_env=False
        ) as client:
            try:
                if channel == "telegram":
                    response = client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={
                            "chat_id": destination,
                            "text": text[:2000],
                            "disable_web_page_preview": True,
                        },
                    )
                    passed = response.status_code == 200 and response.json().get("ok") is True
                elif channel == "healthchecks":
                    response = client.post(heartbeat, content=b"")
                    passed = 200 <= response.status_code < 300
                else:
                    raise ValueError("Choose Telegram or Healthchecks.")
            except (httpx.HTTPError, ValueError):
                passed = False
        return passed

    def test(self, channel):
        if channel not in {"telegram", "healthchecks"}:
            raise ValueError("Choose Telegram or Healthchecks.")
        passed = self.deliver(channel)
        self.store.put("monitoring", channel, {"tested": passed, "timestamp": now()})
        self.store.event("monitoring.test", {"channel": channel, "passed": passed})
        return {
            "passed": passed,
            "detail": "Delivery confirmed by the service."
            if passed
            else "Delivery failed. Check the saved credentials and notification destination.",
        }

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="operations-monitor", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def retry_failed(self):
        count = 0
        for item in self.store.list("notification"):
            if item.get("state") == "failed":
                item.update(state="queued", attempts=0, next_attempt=0)
                self.store.put("notification", item["id"], item)
                count += 1
        self.store.event("notification.retry_requested", {"count": count})
        return {"queued": count}

    def tick(self, clock=None):
        clock = time.time() if clock is None else clock
        if self.status()["configured"]:
            for item in self.store.list("notification"):
                if item.get("state") != "queued" or item.get("next_attempt", 0) > clock:
                    continue
                passed = self.deliver("telegram", item["text"])
                item["attempts"] += 1
                item.update(
                    state="delivered"
                    if passed
                    else "failed"
                    if item["attempts"] >= 8
                    else "queued",
                    next_attempt=clock + min(300, 2 ** item["attempts"]),
                )
                identity = item.get("id")
                if identity:
                    self.store.put("notification", identity, item)
                self.store.event(
                    "notification.delivery", {"passed": passed, "attempt": item["attempts"]}
                )
            if clock >= self.next_heartbeat and self.healthy():
                self.next_heartbeat = clock + 30
                passed = self.deliver("healthchecks")
                self.store.put(
                    "monitoring", "last_heartbeat", {"passed": passed, "timestamp": now()}
                )
        day = datetime.now(UTC).date().isoformat()
        if self.last_backup_day != day:
            path = backup_bundle(self.store, self.store.directory / "backups")
            self.last_backup_day = day
            self.store.event("backup.completed", {"file": path.name, "scheduled": True})

    def _loop(self):
        while not self.stop_event.wait(2):
            try:
                self.tick()
            except Exception:
                # Outbound exceptions may contain credential URLs.
                self.store.event("monitoring.error", {"reason": "delivery_or_backup_failed"})
