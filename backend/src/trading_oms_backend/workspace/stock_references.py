"""Bounded official HKEX reference retrieval off the execution owner thread."""

import hashlib
import io
import queue
import re
import threading
import time
import zipfile
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from defusedxml import ElementTree

from .graph import number
from .stock_sessions import stock_calendar

HKEX_URL = (
    "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
)
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def reference_day(stamp=None):
    day = (stamp or datetime.now(UTC)).astimezone(ZoneInfo("Asia/Hong_Kong")).date()
    return (
        stock_calendar("XHKG")
        .date_to_session(day.isoformat(), direction="previous")
        .date()
        .isoformat()
    )


def parse_hkex(data):
    if len(data) > 4_000_000:
        raise ValueError("Reference download exceeded its limit.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(f.file_size for f in archive.infolist()) > 32_000_000:
            raise ValueError("Reference content exceeded its expanded limit.")
        strings = [
            "".join(n.itertext())
            for n in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).findall(
                "s:si", NS
            )
        ]
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows, day = {}, None
    for row in root.findall(".//s:row", NS):
        fields = {}
        for cell in row.findall("s:c", NS):
            value = cell.find("s:v", NS)
            raw = value.text or "" if value is not None else ""
            fields[re.sub(r"\d", "", cell.get("r", ""))] = (
                strings[int(raw)] if cell.get("t") == "s" and raw else raw
            )
        if fields.get("A", "").startswith("Updated as at "):
            day = (
                datetime.strptime(fields["A"].removeprefix("Updated as at "), "%d/%m/%Y")
                .date()
                .isoformat()
            )
        symbol = fields.get("A", "")
        if not symbol.isdigit() or fields.get("C") not in {"Equity", "Exchange Traded Products"}:
            continue
        raw_lot = fields.get("E", "")
        if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", raw_lot):
            continue
        lot = number(raw_lot.replace(",", ""))
        if lot < 1 or lot % 1:
            continue
        rows[symbol.lstrip("0")] = {
            "symbol": symbol.lstrip("0"),
            "board_lot": str(lot),
            "currency": fields.get("Q"),
            "category": fields.get("C"),
            "stamp_duty": fields.get("H") == "Y",
        }
        if len(rows) > 20000:
            raise ValueError("Reference row limit exceeded.")
    if not day or not rows:
        raise ValueError("Official reference format is unavailable.")
    return {
        "business_date": day,
        "rows": rows,
        "source": "HKEX securities list",
        "url": HKEX_URL,
        "revision": hashlib.sha256(data).hexdigest(),
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def fetch_hkex():
    deadline = time.monotonic() + 15
    chunks, total = [], 0
    with httpx.stream("GET", HKEX_URL, timeout=5, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > 4_000_000 or time.monotonic() > deadline:
                raise ValueError("Official reference request exceeded its bounds.")
            chunks.append(chunk)
    return parse_hkex(b"".join(chunks))


class ReferenceWorker:
    def __init__(self):
        self.results = queue.Queue(maxsize=1)
        self.thread = None
        self.next_attempt = 0.0

    def request(self):
        if (
            self.thread
            and self.thread.is_alive()
            or not self.results.empty()
            or time.monotonic() < self.next_attempt
        ):
            return
        self.next_attempt = time.monotonic() + 60

        def work():
            try:
                result = fetch_hkex()
            except Exception:
                result = {
                    "error": "Official HKEX reference is unavailable; retrying in one minute."
                }
            self.results.put_nowait(result)

        self.thread = threading.Thread(target=work, name="stock-reference", daemon=True)
        self.thread.start()


class StockReferences:
    def stock_reference(self, contract):
        if contract.get("primary_exchange") != "SEHK":
            return None
        worker = getattr(self, "_stock_reference_worker", None)
        if worker is None:
            worker = self._stock_reference_worker = ReferenceWorker()
        try:
            result = worker.results.get_nowait()
        except queue.Empty:
            result = None
        if result:
            self._stock_reference_error = result.get("error")
            if not result.get("error"):
                with self.store.transaction() as db:
                    self.store.write(db, "stock_reference", "HKEX", result)
                    self.store.append(
                        db,
                        "stock.reference.refreshed",
                        {k: v for k, v in result.items() if k != "rows"},
                    )
        record = self.store.get("stock_reference", "HKEX") or {}
        day = reference_day()
        current = (
            record.get("business_date") == day
            and str(record.get("retrieved_at", ""))[:10] == datetime.now(UTC).date().isoformat()
        )
        if not current and self.thread and self.thread.is_alive():
            worker.request()
        row = record.get("rows", {}).get(str(contract.get("symbol", "")).lstrip("0"), {})
        return {
            **{k: v for k, v in record.items() if k != "rows"},
            **row,
            "status": "ready" if current and row else "pending" if not current else "unavailable",
            "detail": getattr(self, "_stock_reference_error", None)
            or "Waiting for current HKEX lot-size reference.",
        }

    def stock_metadata_ready(self, conid):
        c = self.contracts.get(conid, {})
        if c.get("sec_type") != "STK":
            return False
        stamp = datetime.now(UTC)
        day = stamp.astimezone(
            ZoneInfo("Asia/Hong_Kong" if c.get("currency") == "HKD" else "America/New_York")
        ).strftime("%Y%m%d")
        ready = (
            c.get("metadata_instance") == self.process_identity
            and c.get("metadata_epoch") == self.broker.epoch
            and day + ":" in c.get("liquid_hours", "")
            and c.get("market_rule") in self.market_rules
            and getattr(self, "_stock_market_rule_context", {}).get(c.get("market_rule"))
            == (self.process_identity, self.broker.epoch)
        )
        if not ready and self.connected and hasattr(self.broker, "resolve"):
            pending = getattr(self, "_stock_metadata_pending", {})
            self._stock_metadata_pending = pending
            if time.monotonic() >= pending.get(conid, 0):
                pending[conid] = time.monotonic() + 30
                self.broker.resolve(
                    symbol=c.get("symbol", ""),
                    sec_type="STK",
                    exchange=c.get("routing_exchange", c.get("exchange", "")),
                    currency=c.get("currency", ""),
                    conid=conid,
                )
        return bool(ready)
