from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .acceptance import accept_session, session_status
from .audit import audit_detail, audit_page, legacy_page, record_page
from .build_info import build_identity
from .engine import Engine
from .graph import CATALOG, GraphError, compile_graph, crypto_copy, templates
from .idempotency import execute_once
from .legacy import import_history, migrate_definition
from .library import StrategyLibrary
from .market import parse_tick, replay
from .monitoring import Monitoring
from .qualification import accept_review, profiles, save_profile
from .recovery import backup_bundle, restore_bundle
from .reusable import reusable_copy, shared_templates
from .startup import DeferredMigration
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


class FeedRetry(Model):
    components: list[Literal["quote", "trade", "history"]] = Field(min_length=1, max_length=3)
    mutation_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class StockRules(Model):
    rules: dict


class FeeAllowance(Model):
    amount: str = Field(max_length=32)
    revision: int = Field(ge=0)


class Run(Contract):
    execution_policy: Literal["idealpro_funded_fx_v1", "idealpro_broker_candles_v2"] | None = None
    funding_policy: Literal["broker_credit_v1", "paper_buying_power_v1"] | None = None
    session_mode: Literal["regular", "premarket_regular", "fx"] = "regular"
    protection_type: Literal["broker_held", "locally_monitored"] = "broker_held"
    execution_plan_revision: str | None = None
    sizing: dict | None = None
    strategy_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    version: int = Field(ge=1)


class Selection(Model):
    ids: list[str] = Field(min_length=1, max_length=5)
    profile_id: str = Field(default="smoke", pattern=r"^[a-z0-9_-]{1,40}$")
    profile_version: int | None = Field(default=None, ge=1)
    unattended: bool = False
    session_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PaperTestPreview(Contract):
    trading_hours: str = Field(default="extended", pattern=r"^(regular|extended)$")


class PaperTestStart(Model):
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class PreparationRequest(Run):
    lease_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{32,36}$")


class PreparationRelease(Model):
    lease_id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")


class ArchiveSelection(Model):
    ids: list[str] = Field(min_length=1, max_length=50)


class PolicyReplacement(Model):
    target_execution_policy_revision: Literal["idealpro_broker_candles_v2"] | None = None
    ids: list[str] = Field(min_length=1, max_length=5)
    expected_binding_hashes: dict[str, str] = Field(max_length=5)
    target_policy_revision: Literal["broker_credit_v1", "paper_buying_power_v1"]
    mutation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Literal["adopt", "restore"] = "adopt"
    expected_replacement_states: dict[str, str] = Field(default_factory=dict, max_length=5)


class BatchConfirmation(Model):
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    mutation_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class QualificationReview(Model):
    stage: str = Field(pattern=r"^(supervised|unattended)$")
    confirmed: bool


class RecoveryAcknowledgment(Model):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=1)


class IncidentReview(Model):
    rationale: str = Field(default="", max_length=1000)
    revision: int | None = Field(default=None, ge=1)


class Arm(Selection):
    funding_policy_acknowledged: (
        Literal["broker_credit_v1", "paper_buying_power_v1"]
        | list[Literal["broker_credit_v1", "paper_buying_power_v1"]]
        | None
    ) = None
    fx_policy_revision: (
        Literal["idealpro_funded_fx_v1", "idealpro_broker_candles_v2"]
        | list[Literal["idealpro_funded_fx_v1", "idealpro_broker_candles_v2"]]
        | None
    ) = None
    review_fingerprint: str | None = Field(default=None, max_length=64)
    resume_policy: str | None = Field(default=None, pattern=r"^same_engine_routine_v1$")
    local_protection_acknowledged: bool = False
    execution_plan_revisions: dict[str, str] = Field(default_factory=dict)
    mutation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    recovery_acknowledgments: list[RecoveryAcknowledgment] = Field(
        default_factory=list, max_length=200
    )
    review_instance: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


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
    healthchecks_url: str = Field(default="", max_length=200)


class NotificationTest(Model):
    channel: str = Field(pattern=r"^(telegram|healthchecks)$")


class LegacyImport(Model):
    name: str = Field(min_length=1, max_length=100)
    records: list[dict] = Field(min_length=1, max_length=10000)


class LegacyDefinition(Model):
    name: str = Field(min_length=1, max_length=100)
    document: dict


class CryptoImport(LegacyDefinition):
    symbol: str = Field(default="BTC", pattern=r"^(BTC|ETH)$")


def create_app(
    directory: Path,
    pairing_token: str,
    *,
    start_engine=True,
    frontend: Path | None = None,
    development=False,
    port=8000,
    launcher_key=None,
    environment="paper",
    defer_migration=False,
):
    migration = (
        DeferredMigration(directory, directory.parent / "simulation" / "live-crypto")
        if defer_migration
        else None
    )
    store = Store(directory)
    simulation = Store(
        directory.parent / "simulation" if directory.name == "paper" else directory / "simulation"
    )
    engine = Engine(store, environment=environment, migration=migration)
    cookie = engine.environment.cookie
    monitoring = Monitoring(
        store,
        lambda: (
            engine.thread is not None
            and engine.thread.is_alive()
            and time.monotonic() - engine.last_loop < 10
        ),
    )
    sessions: dict[str, float] = {}
    session_actors: dict[str, str] = {}
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
    build = build_identity(frontend)
    engine.build = build
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
            session = request.cookies.get(cookie, "")
            if sessions.get(session, 0) < time.monotonic():
                return JSONResponse(
                    {
                        "detail": "Open start-crypto-sim.ps1 to establish a local session."
                        if engine.environment.crypto
                        else "Open start-paper.ps1 to establish a local session.",
                        "code": "local_session_required",
                    },
                    status_code=401,
                )
            sessions[session] = time.monotonic() + 12 * 60 * 60
            request.state.operator_id = session_actors.setdefault(
                session, "operator-" + uuid.uuid4().hex
            )
        response = await execute_once(request, call_next, store)
        if request.url.path.startswith("/api/") and request.cookies.get(cookie) in sessions:
            response.set_cookie(
                cookie,
                request.cookies[cookie],
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
                **({"dependencies": exc.dependencies} if hasattr(exc, "dependencies") else {}),
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
            "mode": engine.environment.mode,
            "environment": engine.environment.name,
            "engine": bool(engine.thread and engine.thread.is_alive()),
            "build": build,
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
        session_actors[session] = "operator-" + uuid.uuid4().hex
        response = JSONResponse({"authenticated": True})
        response.set_cookie(
            cookie, session, httponly=True, samesite="strict", max_age=12 * 60 * 60, path="/"
        )
        return response

    @app.get("/api/paper/session")
    @app.get("/api/workspace/session")
    def snapshot():
        return engine.call("snapshot")

    @app.get("/api/workspace/overview")
    def overview():
        return engine.call("overview")

    @app.get("/api/workspace/records/{kind}")
    def records(kind: str, before: int | None = None, limit: int = 100):
        return record_page(store, kind, before, limit)

    @app.get("/api/market-data/{conid}/candles")
    def candles(
        conid: int,
        seconds: int = 60,
        before: str | None = None,
        limit: int = 120,
        signal_source: Literal["MIDPOINT", "BID", "ASK"] | None = None,
    ):
        return engine.call(
            "candles",
            conid=conid,
            seconds=seconds,
            before=before,
            limit=limit,
            signal_source=signal_source,
        )

    @app.post("/api/paper/session/connect")
    @app.post("/api/workspace/session/connect")
    def connect():
        return engine.call("connect")

    @app.post("/api/paper/session/attest")
    @app.post("/api/workspace/session/attest")
    def attest(body: Attest):
        return engine.call("attest", confirmed=body.confirmed)

    @app.post("/api/workspace/session/disconnect")
    def disconnect():
        return engine.call("disconnect")

    @app.post("/api/paper/session/reconcile")
    @app.post("/api/workspace/session/reconcile")
    def reconcile():
        return engine.call("begin_reconcile")

    @app.get("/api/market-data/contracts")
    def contracts():
        return engine.call("snapshot")["contracts"]

    @app.post("/api/market-data/resolve")
    def resolve(
        symbol: str = "",
        sec_type: str = "",
        exchange: str = "",
        currency: str = "",
        conid: int | None = None,
    ):
        return engine.call(
            "resolve",
            symbol=symbol,
            sec_type=sec_type,
            exchange=exchange,
            currency=currency,
            conid=conid,
        )

    @app.get("/api/market-data/search/{identity}")
    def search_status(identity: str):
        return engine.call("search_status", identity=identity)

    @app.post("/api/market-data/subscribe")
    def subscribe(body: Contract):
        return engine.call("subscribe", conid=body.conid)

    @app.post("/api/market-data/{conid}/retry")
    def retry_feeds(conid: int, body: FeedRetry, request: Request):
        return engine.call(
            "retry_feeds",
            conid=conid,
            components=body.components,
            mutation_id=body.mutation_id,
            actor=request.state.operator_id,
        )

    @app.get("/api/strategies/catalog")
    def catalog(schema_version: int = 6):
        from .stock_strategies import stock_templates

        items = (
            templates()
            if engine.environment.crypto
            else stock_templates(schema_version)
            if schema_version in (7, 8)
            else shared_templates()
        )
        if engine.environment.crypto:
            items = [{**item, "document": crypto_copy(item["document"])} for item in items]
        return {"blocks": CATALOG, "templates": items, "environment": engine.environment.name}

    @app.post("/api/strategies/convert-stock")
    def convert_stock(body: LegacyDefinition):
        from .stock_strategies import stock_copy

        document = stock_copy(body.document)
        store.backup(store.directory / "backups")
        draft = store.save_draft(None, body.name[:80] + " (stock copy)", document, 0)
        store.event(
            "strategy.stock_copy.created",
            {
                "id": draft["id"],
                "source_schema": body.document.get("schema_version"),
                "source_modified": False,
            },
        )
        return draft

    @app.post("/api/strategies/convert-fx")
    def convert_fx(body: LegacyDefinition):
        from .fx_strategies import fx_copy

        if engine.environment.crypto:
            raise Conflict("Open the paper workspace to create an FX definition.")
        document = fx_copy(body.document)
        store.backup(store.directory / "backups")
        draft = store.save_draft(None, body.name[:80] + " (FX copy)", document, 0)
        store.event(
            "strategy.fx_copy.created",
            {
                "id": draft["id"],
                "source_schema": body.document.get("schema_version"),
                "source_modified": False,
            },
        )
        return draft

    @app.post("/api/contracts/{conid}/stock-rules")
    def stock_rules(conid: int, body: StockRules, request: Request):
        return engine.call(
            "stock_rules", conid=conid, rules=body.rules, actor=request.state.operator_id
        )

    @app.post("/api/runs/prepare-context")
    def prepare_context(body: PreparationRequest):
        return engine.call(
            "prepare_context",
            conid=body.conid,
            session_mode=body.session_mode,
            strategy_id=body.strategy_id,
            version=body.version,
            lease_id=body.lease_id,
            execution_policy=body.execution_policy,
        )

    @app.post("/api/runs/prepare-context/release")
    def release_preparation(body: PreparationRelease):
        return engine.call("release_preparation", lease_id=body.lease_id)

    @app.post("/api/runs/compatibility")
    def stock_compatibility(body: Run):
        return engine.call(
            "stock_compatibility",
            strategy_id=body.strategy_id,
            version=body.version,
            conid=body.conid,
            protection_type=body.protection_type,
            session_mode=body.session_mode,
            sizing=body.sizing,
            funding_policy=body.funding_policy,
            execution_policy=body.execution_policy,
        )

    @app.post("/api/contracts/{conid}/fee-allowance")
    def fee_allowance(conid: int, body: FeeAllowance, request: Request):
        return engine.call(
            "stock_fee",
            conid=conid,
            amount=body.amount,
            revision=body.revision,
            actor=request.state.operator_id,
        )

    @app.post("/api/strategies/convert-crypto")
    def convert_crypto(body: CryptoImport):
        if not engine.environment.crypto:
            raise Conflict("Open the crypto simulator to import a converted copy.")
        document = crypto_copy(body.document, body.symbol)
        draft = store.save_draft(None, body.name[:86] + " (crypto copy)", document, 0)
        store.event(
            "strategy.crypto_copy.created",
            {
                "id": draft["id"],
                "source_schema": body.document.get("schema_version"),
                "source_modified": False,
            },
        )
        return draft

    @app.post("/api/strategies/convert-reusable")
    def convert_reusable(body: LegacyDefinition):
        document = reusable_copy(body.document)
        draft = store.save_draft(None, body.name[:80] + " (reusable copy)", document, 0)
        store.event(
            "strategy.reusable_copy.created",
            {
                "id": draft["id"],
                "source_schema": body.document.get("schema_version"),
                "source_modified": False,
            },
        )
        return draft

    @app.get("/api/strategies")
    def strategies(archived: bool = False):
        return StrategyLibrary(store).listing(archived)

    @app.post("/api/strategies/removal-preview")
    def strategy_removal_preview(body: ArchiveSelection):
        return StrategyLibrary(store).preview(body.ids)

    @app.post("/api/strategies/removal-confirm")
    def strategy_removal_confirm(body: BatchConfirmation, request: Request):
        return StrategyLibrary(store).confirm(
            body.preview_id, body.mutation_id, request.state.operator_id
        )

    @app.post("/api/strategies/{identity}/restore")
    def strategy_restore(identity: str, request: Request):
        return StrategyLibrary(store).restore(identity, request.state.operator_id)

    @app.post("/api/strategies")
    def create_draft(body: Draft):
        if body.revision != 0:
            raise ValueError("A new draft starts at revision zero.")
        return store.save_draft(None, body.name, body.document, 0)

    @app.put("/api/strategies/{identity}")
    def save_draft(identity: str, body: Draft):
        if not store.get("draft", identity):
            if (store.get("strategy_lifecycle", identity) or {}).get("state") == "deleted":
                raise Conflict("This strategy was deleted from the library.")
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

    @app.post("/api/runs/policy-replacement")
    def policy_replacement(body: PolicyReplacement, request: Request):
        return engine.call(
            "policy_replacement", **body.model_dump(), actor=request.state.operator_id
        )

    @app.post("/api/runs/archive-preview")
    def archive_preview(body: ArchiveSelection):
        return engine.call("archive_preview", ids=body.ids)

    @app.post("/api/runs/archive-confirm")
    def archive_confirm(body: BatchConfirmation, request: Request):
        return engine.call("archive_confirm", **body.model_dump(), actor=request.state.operator_id)

    @app.post("/api/runs/arm")
    def arm(body: Arm, request: Request):
        return engine.call("arm", actor=request.state.operator_id, **body.model_dump())

    @app.post("/api/runs/{identity}/disarm")
    def disarm(identity: str):
        return engine.call("disarm", key=identity)

    @app.get("/api/runs/{identity}/removal-preview")
    def removal_preview(identity: str):
        return engine.call("removal_preview", key=identity)

    @app.post("/api/runs/{identity}/remove")
    def remove_run(identity: str):
        return engine.call("remove_run", key=identity)

    @app.get("/api/paper/diagnostics")
    def diagnostics(conid: int):
        return engine.call("connection_diagnostics", conid=conid)

    @app.post("/api/paper/order-tests/preview")
    def paper_test_preview(body: PaperTestPreview):
        return engine.call("paper_test_preview", **body.model_dump())

    @app.post("/api/paper/order-tests")
    def paper_test_start(body: PaperTestStart, request: Request):
        return engine.call("start_paper_test", actor=request.state.operator_id, **body.model_dump())

    @app.get("/api/operations/incidents/{identity}")
    def operation_incident_detail(identity: str):
        return engine.call("incident_detail", identity=identity)

    @app.post("/api/operations/incidents/{identity}/recheck")
    def incident_recheck(identity: str):
        return engine.call("recheck_incident", identity=identity)

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

    @app.get("/api/events/legacy/{identity}/page")
    def legacy_records_page(identity: str, after: int = 0):
        return legacy_page(store, identity, after)

    @app.get("/api/events/legacy/{identity}/detail/{sequence}")
    def legacy_record_detail(identity: str, sequence: int):
        record = store.get("legacy_record", f"{identity}:{sequence}")
        if not record:
            raise ValueError("Historical event not found.")
        return record

    @app.post("/api/events/legacy")
    def legacy_import(body: LegacyImport):
        return import_history(store, body.name, body.records)

    @app.post("/api/strategies/import-legacy")
    def legacy_definition(body: LegacyDefinition):
        return migrate_definition(store, body.name, body.document)

    @app.get("/api/operations/orders/{identity}")
    def order_detail(identity: str):
        return engine.call("order_detail", identity=identity)

    @app.get("/api/events/page")
    def event_page(
        before: int | None = None,
        after: int | None = None,
        q: str = "",
        limit: int = 200,
        watermark: int | None = None,
    ):
        return audit_page(store, before=before, after=after, q=q, limit=limit, watermark=watermark)

    @app.get("/api/events/detail/{sequence}")
    def event_detail(sequence: int):
        return audit_detail(store, sequence)

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
    async def event_stream(request: Request, after: int = 0, summaries: bool = False):
        last = request.headers.get("last-event-id", "")
        cursor = max(0, int(last) if last.isdecimal() else after)

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                if summaries:
                    page = await asyncio.to_thread(audit_page, store, after=cursor)
                    if page["latest"] - cursor > 2000:
                        yield (
                            "event: resync\ndata: "
                            '{"reason":"Older events remain available in history."}\n\n'
                        )
                        return
                    items = page["items"]
                else:
                    items = await asyncio.to_thread(store.events, cursor)
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
    def incident_review(identity: str, request: Request, body: IncidentReview | None = None):
        return engine.call(
            "review_incident",
            identity=identity,
            actor=request.state.operator_id,
            **(body or IncidentReview()).model_dump(),
        )

    @app.get("/api/incidents")
    def incidents(view: str = "current", before: int | None = None, limit: int = 200):
        return engine.call("incident_page", view=view, before=before, limit=limit)

    @app.post("/api/incidents/recovery-preview")
    def recovery_preview():
        return engine.call("recovery_batch_preview")

    @app.post("/api/incidents/recovery-confirm")
    def recovery_confirm(body: BatchConfirmation, request: Request):
        return engine.call(
            "recovery_batch_confirm", **body.model_dump(), actor=request.state.operator_id
        )

    @app.get("/api/incidents/recovery-status")
    def recovery_status():
        return engine.call("recovery_status")

    @app.get("/api/incidents/{identity}")
    def incident_detail(identity: str):
        return engine.call("incident_detail", identity=identity)

    @app.post("/api/incidents/{identity}/investigation/close")
    def close_investigation(identity: str, body: IncidentReview, request: Request):
        return engine.call(
            "close_investigation",
            identity=identity,
            actor=request.state.operator_id,
            **body.model_dump(),
        )

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
        return profiles(store, simulation=engine.environment.crypto)

    @app.post("/api/risk-profiles")
    def profile(body: dict):
        return save_profile(store, body, simulation=engine.environment.crypto)

    @app.get("/api/operations/qualification")
    def qualification():
        return {
            "environment": engine.environment.name,
            "verified_build": engine.code_verified,
            "broker_evidence": store.get("qualification", "broker_evidence") or {},
            "operator_review": store.get("qualification", "operator_review") or {},
            **session_status(store),
        }

    @app.post("/api/operations/qualification")
    def qualification_review(body: QualificationReview):
        if engine.environment.crypto:
            raise Conflict("Local simulation cannot qualify IBKR paper execution.")
        return accept_review(store, body.stage, body.confirmed)

    @app.post("/api/operations/qualification/sessions/{day}")
    def session_review(day: str, body: dict):
        if engine.environment.crypto:
            raise Conflict("Local simulation cannot qualify IBKR paper execution.")
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
