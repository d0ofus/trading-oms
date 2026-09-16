from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .acceptance import accept_session, session_status
from .engine import Engine
from .graph import CATALOG, GraphError, compile_graph, templates
from .idempotency import execute_once
from .legacy import import_history, migrate_definition
from .market import parse_tick, replay
from .monitoring import Monitoring
from .qualification import accept_review, profiles, save_profile
from .recovery import backup_bundle, restore_bundle
from .store import Conflict, Store, now


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Pair(Model):
    token: str = Field(min_length=24, max_length=200)


class Draft(Model):
    name: str = Field(min_length=1, max_length=100)
    document: dict
    revision: int = Field(ge=0)


class Revision(Model):
    revision: int = Field(ge=1)


class Graph(Model):
    document: dict


class Attest(Model):
    confirmed: bool


class Contract(Model):
    conid: int = Field(gt=0)


class Run(Contract):
    strategy_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    version: int = Field(ge=1)


class Selection(Model):
    ids: list[str] = Field(min_length=1, max_length=5)
    profile_id: str = Field(default="smoke", pattern=r"^[a-z0-9_-]{1,40}$")
    profile_version: int = Field(default=1, ge=1)
    unattended: bool = False


class QualificationReview(Model):
    stage: str = Field(pattern=r"^(supervised|unattended)$")
    confirmed: bool


class Arm(Selection):
    mutation_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class Emergency(Model):
    active: bool
    reviewed: bool = False


class Dataset(Model):
    name: str = Field(min_length=1, max_length=100)
    ticks: list[dict] = Field(min_length=2, max_length=250000)
    source: str = Field(pattern=r"^(recorded_ticks|synthetic_fixture)$")


class ReplayRequest(Model):
    strategy_id: str
    version: int = Field(ge=1)
    dataset_id: str


class MonitorConfiguration(Model):
    telegram_token: str = Field(max_length=200)
    telegram_chat: str = Field(max_length=30)
    healthchecks_url: str = Field(max_length=200)


class NotificationTest(Model):
    channel: str = Field(pattern=r"^(telegram|healthchecks)$")


class LegacyImport(Model):
    name: str = Field(min_length=1, max_length=100)
    records: list[dict] = Field(min_length=1, max_length=10000)


class LegacyDefinition(Model):
    name: str = Field(min_length=1, max_length=100)
    document: dict


def create_app(
    directory: Path,
    pairing_token: str,
    *,
    start_engine=True,
    frontend: Path | None = None,
    development=False,
    port=8000,
    launcher_key=None,
):
    store = Store(directory)
    simulation = Store(
        directory.parent / "simulation" if directory.name == "paper" else directory / "simulation"
    )
    engine = Engine(store)
    monitoring = Monitoring(
        store,
        lambda: (
            engine.thread is not None
            and engine.thread.is_alive()
            and time.monotonic() - engine.last_loop < 10
        ),
    )
    sessions: dict[str, float] = {}
    unused_pairing = pairing_token

    @asynccontextmanager
    async def lifespan(app):
        if start_engine:
            engine.start()
            monitoring.start()
        try:
            yield
        finally:
            # Disarm execution before waiting for notification network timeouts.
            engine.stop()
            monitoring.stop()

    app = FastAPI(
        title="Trading OMS paper workspace",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.store, app.state.engine = store, engine
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if development:
        hosts |= {"127.0.0.1:5173", "localhost:5173"}
    origins = {"http://" + host for host in hosts}

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        if request.headers.get("host") not in hosts:
            return JSONResponse({"detail": "Use the local application launcher."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            return JSONResponse(
                {"detail": "Only the local workspace origin is permitted."}, status_code=403
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if origin not in origins:
                return JSONResponse(
                    {"detail": "A local workspace origin is required."}, status_code=403
                )
            length = request.headers.get("content-length", "")
            if not length.isdecimal() or int(length) > 32 * 1024 * 1024:
                return JSONResponse(
                    {"detail": "Request exceeds the workspace size limit."}, status_code=413
                )
        if request.url.path.startswith("/api/") and request.url.path != "/api/auth/pair":
            session = request.cookies.get("oms_session", "")
            if sessions.get(session, 0) < time.monotonic():
                return JSONResponse(
                    {
                        "detail": "Open start-paper.ps1 to establish a local session.",
                        "code": "local_session_required",
                    },
                    status_code=401,
                )
            sessions[session] = time.monotonic() + 12 * 60 * 60
        response = await execute_once(request, call_next, store)
        if request.url.path.startswith("/api/") and request.cookies.get("oms_session") in sessions:
            response.set_cookie(
                "oms_session",
                request.cookies["oms_session"],
                httponly=True,
                samesite="strict",
                max_age=12 * 60 * 60,
                path="/",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            {
                "detail": "Check the highlighted fields.",
                "issues": [
                    {
                        "code": "invalid_field",
                        "field": ".".join(str(p) for p in e["loc"]),
                        "message": e["msg"],
                        "remediation": "Correct this field and retry.",
                    }
                    for e in exc.errors()
                ],
            },
            status_code=422,
        )

    @app.exception_handler(ValueError)
    async def invalid_operation(request, exc):
        return JSONResponse(
            {
                "detail": str(exc),
                "issues": [
                    {
                        "code": "conflict"
                        if isinstance(exc, Conflict)
                        else "invalid_strategy"
                        if isinstance(exc, GraphError)
                        else "action_blocked",
                        "message": str(exc),
                        "node": getattr(exc, "node", None),
                        "remediation": "Review the relevant configuration or readiness check.",
                    }
                ],
            },
            status_code=409 if isinstance(exc, Conflict) else 422,
        )

    @app.get("/healthz")
    def health():
        return {
            "status": "running" if not engine.stopping.is_set() else "stopped",
            "mode": "paper",
            "engine": bool(engine.thread and engine.thread.is_alive()),
        }

    @app.post("/api/auth/pair")
    def pair(body: Pair):
        nonlocal unused_pairing
        if not (
            (unused_pairing and secrets.compare_digest(body.token, unused_pairing))
            or (launcher_key and secrets.compare_digest(body.token, launcher_key))
        ):
            return JSONResponse(
                {"detail": "This launcher link has expired. Restart the local launcher."},
                status_code=401,
            )
        unused_pairing = ""
        session = secrets.token_urlsafe(32)
        sessions[session] = time.monotonic() + 12 * 60 * 60
        response = JSONResponse({"authenticated": True})
        response.set_cookie(
            "oms_session", session, httponly=True, samesite="strict", max_age=12 * 60 * 60, path="/"
        )
        return response

    @app.get("/api/paper/session")
    def snapshot():
        return engine.call("snapshot")

    @app.post("/api/paper/session/connect")
    def connect():
        return engine.call("connect")

    @app.post("/api/paper/session/attest")
    def attest(body: Attest):
        return engine.call("attest", confirmed=body.confirmed)

    @app.post("/api/paper/session/reconcile")
    def reconcile():
        return engine.call("begin_reconcile")

    @app.get("/api/market-data/contracts")
    def contracts():
        return engine.call("snapshot")["contracts"]

    @app.post("/api/market-data/resolve")
    def resolve(symbol: str):
        return engine.call("resolve", symbol=symbol)

    @app.post("/api/market-data/subscribe")
    def subscribe(body: Contract):
        return engine.call("subscribe", conid=body.conid)

    @app.get("/api/strategies/catalog")
    def catalog():
        return {"blocks": CATALOG, "templates": templates()}

    @app.get("/api/strategies")
    def strategies():
        return store.list("draft")

    @app.post("/api/strategies")
    def create_draft(body: Draft):
        if body.revision != 0:
            raise ValueError("A new draft starts at revision zero.")
        return store.save_draft(None, body.name, body.document, 0)

    @app.put("/api/strategies/{identity}")
    def save_draft(identity: str, body: Draft):
        if not store.get("draft", identity):
            raise ValueError("Draft not found.")
        return store.save_draft(identity, body.name, body.document, body.revision)

    @app.post("/api/strategies/validate")
    def validate(body: Graph):
        graph = compile_graph(body.document)
        return {"valid": True, "hash": graph.digest, "explanation": graph.explain(), "issues": []}

    @app.post("/api/strategies/{identity}/publish")
    def publish(identity: str, body: Revision):
        return store.publish(identity, body.revision)

    @app.get("/api/strategies/{identity}/versions")
    def versions(identity: str):
        return store.versions(identity)

    @app.get("/api/strategies/{identity}/versions/{version}")
    def published_version(identity: str, version: int):
        return store.version(identity, version)

    @app.post("/api/runs")
    def create_run(body: Run):
        return engine.call("create_run", **body.model_dump())

    @app.post("/api/runs/arm-preview")
    def preview(body: Selection):
        return engine.call("arm_preview", **body.model_dump())

    @app.post("/api/runs/arm")
    def arm(body: Arm):
        return engine.call("arm", **body.model_dump())

    @app.post("/api/runs/{identity}/disarm")
    def disarm(identity: str):
        return engine.call("disarm", key=identity)

    @app.post("/api/operations/emergency")
    def emergency(body: Emergency):
        if not body.active and not body.reviewed:
            raise ValueError(
                "Review the account and fresh authorization before clearing emergency stop."
            )
        if body.active:
            store.set_emergency(True)
        return engine.call("emergency", active=body.active)

    @app.post("/api/operations/orders/{identity}/cancel")
    def cancel_entry(identity: str):
        return engine.call("cancel_entry", key=identity)

    @app.post("/api/operations/positions/{identity}/close")
    def close_position(identity: str):
        return engine.call("close_position", key=identity)

    @app.get("/api/events/legacy")
    def legacy_imports():
        return store.list("legacy_import")

    @app.get("/api/events/legacy/{identity}")
    def legacy_records(identity: str):
        return [r for r in store.list("legacy_record") if r["import_id"] == identity]

    @app.post("/api/events/legacy")
    def legacy_import(body: LegacyImport):
        return import_history(store, body.name, body.records)

    @app.post("/api/strategies/import-legacy")
    def legacy_definition(body: LegacyDefinition):
        return migrate_definition(store, body.name, body.document)

    @app.get("/api/operations/orders/{identity}")
    def order_detail(identity: str):
        return engine.call("order_detail", identity=identity)

    @app.get("/api/events")
    def events(after: int = 0, q: str = ""):
        if len(q) > 200:
            raise ValueError("Keep audit searches under 200 characters.")
        if not q:
            return store.events(max(0, after))
        with store.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE sequence>? AND "
                "(instr(lower(type),lower(?))>0 OR instr(lower(payload),lower(?))>0) "
                "ORDER BY sequence LIMIT 200",
                (max(0, after), q, q),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    @app.post("/api/market-data/unsubscribe")
    def unsubscribe(body: Contract):
        return engine.call("unsubscribe", conid=body.conid)

    @app.get("/api/events/stream")
    async def event_stream(request: Request, after: int = 0):
        last = request.headers.get("last-event-id", "")
        cursor = max(0, int(last) if last.isdecimal() else after)

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                items = store.events(cursor)
                for item in items:
                    cursor = item["sequence"]
                    yield f"id: {cursor}\nevent: journal\ndata: {json.dumps(item)}\n\n"
                if not items:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/notifications")
    def monitoring_status():
        return monitoring.status()

    @app.post("/api/notifications/configure")
    def monitoring_configuration(body: MonitorConfiguration):
        return monitoring.configure(body.telegram_token, body.telegram_chat, body.healthchecks_url)

    @app.post("/api/notifications/test")
    def notification_test(body: NotificationTest):
        return monitoring.test(body.channel)

    @app.post("/api/notifications/retry")
    def notification_retry():
        return monitoring.retry_failed()

    @app.post("/api/operations/incidents/{identity}/review")
    def incident_review(identity: str):
        return engine.call("review_incident", identity=identity)

    @app.get("/api/preferences")
    def preferences():
        return store.get("preferences", "workspace") or {}

    @app.put("/api/preferences")
    def save_preferences(body: dict):
        if len(json.dumps(body)) > 20000 or set(body) - {
            "theme",
            "density",
            "panels",
            "tables",
            "setup",
            "selected_strategy",
            "view",
            "filters",
        }:
            raise ValueError("Unsupported workspace preference.")
        store.put("preferences", "workspace", body)
        return body

    @app.get("/api/risk-profiles")
    def risk_profiles():
        return profiles(store)

    @app.post("/api/risk-profiles")
    def profile(body: dict):
        return save_profile(store, body)

    @app.get("/api/operations/qualification")
    def qualification():
        return {
            "verified_build": engine.code_verified,
            "broker_evidence": store.get("qualification", "broker_evidence") or {},
            "operator_review": store.get("qualification", "operator_review") or {},
            **session_status(store),
        }

    @app.post("/api/operations/qualification")
    def qualification_review(body: QualificationReview):
        return accept_review(store, body.stage, body.confirmed)

    @app.post("/api/operations/qualification/sessions/{day}")
    def session_review(day: str, body: dict):
        return accept_session(store, day, body.get("confirmed"))

    @app.get("/api/testing/datasets")
    def datasets():
        return simulation.list("dataset")

    @app.post("/api/testing/datasets")
    def dataset(body: Dataset):
        previous = None
        for tick in body.ticks:
            stamp, _, _ = parse_tick(tick)
            if previous and stamp < previous:
                raise ValueError("The dataset contains out-of-order observations.")
            previous = stamp
        identity = uuid.uuid4().hex
        capture = simulation.capture(body.ticks)
        record = {
            "id": identity,
            "name": body.name,
            "source": body.source,
            "ticks": len(body.ticks),
            "capture": capture,
            "created_at": now(),
        }
        simulation.put("dataset", identity, record)
        simulation.event("dataset.imported", record)
        return record

    @app.post("/api/testing/replay")
    def run_replay(body: ReplayRequest):
        published = store.version(body.strategy_id, body.version)
        dataset = simulation.get("dataset", body.dataset_id)
        if not dataset:
            raise ValueError("Choose a recorded-tick dataset first.")
        ticks = simulation.load_capture(dataset["capture"])
        identity = uuid.uuid4().hex
        result = replay(
            compile_graph(published["document"]), ticks, simulation.directory / "replays" / identity
        )
        result.update(
            id=identity,
            strategy_name=published["name"],
            strategy_id=body.strategy_id,
            version=body.version,
            dataset=dataset["name"],
            dataset_source=dataset["source"],
            timestamp=now(),
        )
        simulation.put("replay", identity, result)
        simulation.event(
            "replay.completed",
            {
                "id": identity,
                "strategy_hash": result["strategy_hash"],
                "capture": dataset["capture"],
            },
        )
        return result

    @app.get("/api/testing/results")
    def replay_results():
        return simulation.list("replay")

    @app.post("/api/operations/restore-test")
    def restore_test():
        backup = backup_bundle(store, directory / "backups")
        target = directory / "restore-tests" / uuid.uuid4().hex
        result = restore_bundle(backup, target)
        store.put(
            "qualification",
            "restore_test",
            {"timestamp": now(), "passed": True, "backup": backup.name},
        )
        store.event("backup.restore_test", {"passed": True, "entries_disarmed": True})
        return {
            "detail": "Backup restored separately, verified, and stopped for recovery review.",
            "verification": result,
        }

    @app.post("/api/operations/backup")
    def backup():
        path = backup_bundle(store, store.directory / "backups")
        store.event("backup.completed", {"file": path.name})
        return {"file": path.name, "integrity": "ok"}

    if frontend and (frontend / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}")
        def workspace(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Unknown workspace API."}, status_code=404)
            return FileResponse(frontend / "index.html")

    return app
