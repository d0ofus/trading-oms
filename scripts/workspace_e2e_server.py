"""Isolated browser-test service. Its broker cannot open a socket or send orders."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import json
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

import uvicorn  # noqa: E402 - resolve the checked-out backend above, not another installed copy.
from trading_oms_backend.workspace.api import create_app  # noqa: E402
from trading_oms_backend.workspace.broker import PaperGateway  # noqa: E402


class OfflineBroker(PaperGateway):
    def connect(self):
        raise ValueError("Broker networking is disabled in browser verification.")

    def subscribe(self, conid):
        pass

    def submit_bracket(self, intent):
        raise AssertionError("Browser verification must never submit broker orders.")

    def submit_exit(self, intent):
        raise AssertionError("Browser verification must never submit broker orders.")

    def cancel(self, broker_id):
        raise AssertionError("Browser verification must never mutate a broker order.")


with tempfile.TemporaryDirectory(
    prefix="oms-browser-", ignore_cleanup_errors=True
) as temporary:
    executable = Path(
        subprocess.check_output(
            [
                "node",
                "-e",
                "process.stdout.write(require('playwright').chromium.executablePath())",
            ],
            cwd=ROOT / "frontend",
            text=True,
        )
    )
    # Use Playwright's matching headless shell, which has no desktop startup
    # services or browser UI. Keep its revision tied to the installed package.
    browser_manifest = json.loads(
        (ROOT / "frontend/node_modules/playwright-core/browsers.json").read_text()
    )
    shell_revision = next(
        item["revision"]
        for item in browser_manifest["browsers"]
        if item["name"] == "chromium-headless-shell"
    )
    shell_root = executable.parents[2] / f"chromium_headless_shell-{shell_revision}"
    shell_name = (
        "chrome-headless-shell.exe" if os.name == "nt" else "chrome-headless-shell"
    )
    executable = next(
        (path for path in shell_root.rglob(shell_name) if path.is_file()),
        shell_root / shell_name,
    )
    if not executable.exists():
        raise RuntimeError(
            "Install the verification browser: cd frontend; npx playwright install chromium"
        )
    browser = subprocess.Popen(
        [
            str(executable),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-proxy-server",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-component-update",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--enable-automation",
            "--no-default-browser-check",
            "--no-first-run",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={Path(temporary) / 'browser'}",
            "about:blank",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    app = create_app(
        Path(temporary),
        "synthetic-browser-pairing-for-tests-only",
        start_engine=False,
        frontend=ROOT / "frontend" / "dist",
        port=8013,
    )
    engine = app.state.engine
    engine.code_verified = False  # Stable fixture; never claim a real release gate.
    engine.broker = OfflineBroker(engine.observations)
    engine.contracts[100] = {
        "conid": 100,
        "symbol": "AAPL",
        "name": "Synthetic contract fixture for browser verification",
        "exchange": "NASDAQ",
        "min_tick": "0.01",
    }
    try:
        # The HTTP fixture must not advertise readiness before the independent
        # browser exposes CDP (cold Windows browser startup can take longer).
        deadline = time.monotonic() + 45
        opener = build_opener(ProxyHandler({}))
        port_file = Path(temporary) / "browser" / "DevToolsActivePort"
        while True:
            if browser.poll() is not None:
                raise RuntimeError(
                    "The isolated verification browser exited during startup."
                )
            try:
                debug_port = int(port_file.read_text(encoding="utf-8").splitlines()[0])
                with opener.open(
                    f"http://127.0.0.1:{debug_port}/json/version", timeout=1
                ) as response:
                    if response.status == 200:
                        endpoint = json.load(response)["webSocketDebuggerUrl"]
                        break
            except (URLError, TimeoutError, OSError, ValueError, IndexError):
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "The isolated verification browser did not become ready."
                )
            time.sleep(0.2)

        @app.get("/browser-endpoint")
        def browser_endpoint():
            return {"endpoint": endpoint}

        # Place the fixture route ahead of the production SPA catch-all.
        app.router.routes.insert(0, app.router.routes.pop())

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8013,
            access_log=False,
            log_level="warning",
            timeout_graceful_shutdown=3,
        )
    finally:
        if os.name == "nt" and browser.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(browser.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif browser.poll() is None:
            browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()
