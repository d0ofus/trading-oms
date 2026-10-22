"""Bounded, read-only paper observations for the offline migration guard."""

import queue
import threading
import time

from .broker import GatewayData
from .store import Conflict, now

SNAPSHOT_ENDS = frozenset(
    {"positions_end", "orders_end", "completed_orders_end", "executions_end", "account_end"}
)
FARM_INFORMATION = {2104, 2106, 2107, 2108, 2119, 2158}
CONNECTION_ERRORS = {1100, 1101, 1102, 1300, 502, 504}


def collect_snapshot(*, broker_factory=None, timeout=30, cancelled=None):
    observations = queue.Queue(maxsize=8192)
    broker = (broker_factory or GatewayData)(observations)
    parts, positions, orders, executions, facts = set(), {}, [], [], {}
    handshake = paper = requested = False
    deadline = time.monotonic() + timeout

    def connect():
        try:
            broker.connect()
        except Exception:
            # Never forward SDK exception text: it can include broker identifiers.
            try:
                observations.put_nowait({"type": "connect_failed", "epoch": broker.epoch})
            except queue.Full:
                broker.overflow.set()

    worker = threading.Thread(target=connect, name="migration-read-only", daemon=True)
    worker.start()
    try:
        while time.monotonic() < deadline:
            if cancelled is not None and cancelled.is_set():
                raise Conflict("Migration check cancelled. Connect paper Gateway when ready.")
            if broker.overflow.is_set():
                raise Conflict("Migration check overflowed; a complete fresh snapshot is required.")
            try:
                event = observations.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if event.get("epoch") != broker.epoch:
                continue
            kind = event["type"]
            if kind == "handshake":
                handshake = True
            elif kind == "account_context":
                if requested and not broker.can_resume_attestation:
                    raise Conflict(
                        "The account context changed during the migration snapshot; retry."
                    )
                if event.get("paper") is not True or event.get("count") != 1:
                    raise Conflict("Migration requires exactly one verified paper account.")
                paper = True
            elif kind in {"disconnected", "connect_failed"}:
                raise Conflict(
                    "Cannot complete the read-only migration check. Open the paper Gateway "
                    "with its API on 127.0.0.1:4002, then click Connect paper Gateway again. "
                    "Check the pinned SDK installation if Gateway is already available."
                )
            elif kind == "broker_error":
                code = event["code"]
                if code in CONNECTION_ERRORS or (
                    event.get("context") != "pnl" and code not in FARM_INFORMATION
                ):
                    raise Conflict(
                        f"Read-only migration check received Gateway code {code}. "
                        "Verify the paper login and API on 127.0.0.1:4002, then retry."
                    )
            elif requested:
                if kind in SNAPSHOT_ENDS:
                    parts.add(kind)
                elif kind == "position":
                    positions[event.get("own_account"), event["conid"]] = event
                elif kind == "open_order":
                    orders.append(event)
                elif kind == "execution":
                    executions.append(event)
                elif kind == "account_fact":
                    facts[event["tag"]] = event["value"]
            if handshake and paper and not requested:
                if not broker.paper_context:
                    raise Conflict("The paper context changed during the migration check.")
                # Pin the account inside the data-only adapter. This does not grant
                # execution: its SDK write methods remain disabled, even when attested.
                broker.attest()
                broker.reconcile()
                requested = True
            if SNAPSHOT_ENDS <= parts and observations.empty():
                if (
                    not broker.paper_context
                    or not broker.can_resume_attestation
                    or not broker.client.isConnected()
                    or broker.overflow.is_set()
                ):
                    raise Conflict("The migration snapshot lost its verified paper connection.")
                return {
                    "source": "read_only_gateway",
                    "observed_at": now(),
                    "paper": True,
                    "complete": sorted(parts),
                    "positions": list(positions.values()),
                    "broker_orders": orders,
                    "executions": executions,
                    "account_facts": facts,
                }
        raise Conflict(
            "Read-only migration check timed out before all snapshot streams completed. "
            "Open the paper Gateway API on 127.0.0.1:4002 and click Connect paper Gateway again."
        )
    except Conflict:
        raise
    except Exception:
        raise Conflict(
            "The read-only migration request failed. Check the paper Gateway API and "
            "pinned SDK installation, then retry. No broker orders were sent."
        ) from None
    finally:
        try:
            broker.disconnect()
        except Exception:
            raise Conflict(
                "Could not close the read-only connection. Stop the launcher and retry."
            ) from None
        finally:
            worker.join(timeout=1)
