from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn

from .api import create_app
from .monitoring import Vault


@contextmanager
def exclusive_owner(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "engine.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            if stream.read(1) == b"":
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("A workspace engine already owns this state directory.") from exc
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    parser = argparse.ArgumentParser(
        description="Local paper workspace; never binds a public interface."
    )
    parser.add_argument("--state", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--development", action="store_true")
    parser.add_argument(
        "--no-watchdog", action="store_true", help="For isolated automated tests only."
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a local unprivileged application port.")
    directory = (
        args.state
        or Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
        / "TradingOMS"
        / "paper"
    )
    frontend = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    if not args.development and not (frontend / "index.html").exists():
        parser.error("Build the frontend first: npm --prefix frontend run build")
    token = secrets.token_urlsafe(32)
    vault = Vault(
        "TradingOMS/launcher/" + hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:24]
    )
    if args.open and os.name == "nt":
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                running = client.get(f"http://127.0.0.1:{args.port}/healthz")
            previous_key = vault.read("session_key")
            if running.is_success and running.json().get("engine") and previous_key:
                webbrowser.open(f"http://127.0.0.1:{args.port}/desk#pair=" + previous_key)
                return
        except (httpx.HTTPError, ValueError):
            pass
    with exclusive_owner(directory):
        if os.name == "nt":
            vault.write("session_key", token)
        app = create_app(
            directory,
            token,
            frontend=frontend,
            development=args.development,
            port=args.port,
            launcher_key=token if os.name == "nt" else None,
        )
        stop = threading.Event()
        supervisor = None
        if not args.no_watchdog:
            supervisor = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "trading_oms_backend.workspace.watchdog",
                    "--state",
                    str(directory.resolve()),
                    "--pid",
                    str(os.getpid()),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

        def open_window():
            origin = f"http://127.0.0.1:{args.port}"
            for _ in range(60):
                if stop.wait(0.5):
                    return
                try:
                    with httpx.Client(timeout=1, trust_env=False) as client:
                        response = client.get(origin + "/healthz")
                    if response.is_success:
                        webbrowser.open(origin + "/desk#pair=" + token)
                        return
                except httpx.HTTPError:
                    continue

        if args.open:
            threading.Thread(target=open_window, name="workspace-launcher", daemon=True).start()
        try:
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=args.port,
                access_log=False,
                log_level="warning",
                timeout_graceful_shutdown=5,
            )
        finally:
            stop.set()
            if supervisor:
                supervisor.terminate()
                supervisor.wait(timeout=5)
            # Clearing this thread's power request happens in the engine thread.
            time.sleep(0.05)


if __name__ == "__main__":
    main()
