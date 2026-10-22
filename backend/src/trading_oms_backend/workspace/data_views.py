"""Display-only candle aggregation. Never feeds strategy entry evaluation."""

import time
from datetime import UTC, datetime

from .graph import number


class DataViews:
    def feed_health(self, conid, run=None):
        if self._fx_run(run) or conid in getattr(self, "fx_data", {}):
            return self._fx_feed_health(conid, run)
        from .premarket import premarket

        history_ready = (
            self._run_history_ready(run) if run else bool(self.data.get(conid, {}).get("warm"))
        )
        data, quotes = self.data.get(conid, {}), self.quotes.get(conid, {})

        def age(value):
            try:
                return (datetime.now(UTC) - datetime.fromisoformat(value)).total_seconds()
            except (ValueError, TypeError):
                return None

        ages = {
            "last": age(data.get("received_at")),
            "source": age(data.get("source_at")),
            "bid": age(quotes.get("bid", {}).get("received_at")),
            "ask": age(quotes.get("ask", {}).get("received_at")),
        }
        fresh = all(value is not None and 0 <= value <= 15 for value in ages.values())
        fresh = fresh and all(
            number(quotes.get(side, {}).get("price", 0)) > 0 for side in ("bid", "ask")
        )
        ready = bool(fresh and data.get("live") and history_ready)
        issues = []
        for component, state in self.feed_projection(conid).items():
            if (
                run
                and (premarket(run) or not self._requires_downloaded_history(run))
                and component == "history"
            ):
                continue
            if state["status"] == "failed":
                ready = False
                diagnostic = state.get("diagnostic") or {}
                detail = diagnostic.get("detail", "Retry after checking broker diagnostics")
                issues.append(f"{component.title()} feed rejected: {detail}")
        if not data.get("live"):
            issues.append(data.get("diagnostic") or "Live subscription is unavailable")
        if not history_ready:
            issues.append("History coverage is not ready")
        for field, seconds in ages.items():
            if seconds is None:
                issues.append(f"{field.title()} observation is missing")
            elif not 0 <= seconds <= 15:
                issues.append(f"{field.title()} observation age is {seconds:.1f}s (limit 15s)")
        for side in ("bid", "ask"):
            if number(quotes.get(side, {}).get("price", 0)) <= 0:
                issues.append(f"{side.title()} price is unavailable")
        return {
            "ages": ages,
            "history_ready": history_ready,
            "status": "ready"
            if ready
            else "blocked"
            if any("rejected" in i for i in issues)
            else "waiting",
            "execution_fresh": ready,
            "execution_detail": "Fresh execution observations available."
            if ready
            else "; ".join(issues) + ". New entries wait for valid observations.",
            "subscription_health": data.get("subscription_status")
            or ("live" if data.get("live") else "unavailable"),
        }

    def candles(self, conid, seconds=60, before=None, limit=120, signal_source=None):
        if conid not in self.data or seconds not in (5, 60, 300) or not 1 <= limit <= 120:
            raise ValueError(
                "Select a subscribed contract and supported candle interval (maximum 120 rows)."
            )
        if conid in getattr(self, "fx_data", {}):
            return self._fx_candles(conid, seconds, before, limit, signal_source)
        cache = getattr(self, "_candle_cache", {})
        key = (conid, seconds, before, limit)
        if key in cache and time.monotonic() - cache[key][0] < 2:
            return cache[key][1]
        rows = self._display_candles(conid, seconds=seconds, before=before, limit=limit + 1)[
            str(seconds)
        ]
        result = {
            "items": rows[-limit:],
            "next_cursor": rows[-limit]["timestamp"] if len(rows) > limit else None,
        }
        if len(cache) >= 6:
            del cache[min(cache, key=lambda k: cache[k][0])]
        cache[key] = (time.monotonic(), result)
        self._candle_cache = cache
        return result

    def _display_candles(self, conid, seconds=None, before=None, limit=120):
        history = self.history_bars.get(conid, {5: {}, 60: {}})
        extended = getattr(self, "premarket_history", {}).get(conid, {}).get("bars", {})
        history = {
            interval: {**extended.get(interval, {}), **history[interval]} for interval in (5, 60)
        }
        realtime = self.display_bars.get(conid, {})
        result = {}
        intervals = (seconds,) if seconds else (5, 60, 300)
        for seconds in intervals:
            base = 60 if seconds == 300 else seconds
            source_rows = dict(history[base])
            if realtime:
                fine = {**history[5], **realtime}
                fine_start = (
                    min(int(row["timestamp"]) for row in fine.values()) // seconds * seconds
                )
                source_rows = {
                    key: {**row, "_display_seconds": 60}
                    for key, row in history[60].items()
                    if seconds >= 60 and int(row["timestamp"]) < fine_start
                }
                source_rows.update(fine)
                base = 5
            boundary = datetime.fromisoformat(before).timestamp() if before else float("inf")
            rows = sorted(
                (b for b in source_rows.values() if int(b["timestamp"]) < boundary),
                key=lambda b: int(b["timestamp"]),
            )
            buckets = {}
            for row in rows:
                start = int(row["timestamp"]) // seconds * seconds
                bucket = buckets.get(start)
                volume = number(row["volume"]) if row.get("volume") is not None else None
                if (
                    volume is not None
                    and volume < 0
                    and self.contracts.get(conid, {}).get("stock_rules")
                ):
                    volume = None
                if bucket is None:
                    buckets[start] = {
                        "timestamp": start,
                        "open": number(row["open"]),
                        "high": number(row["high"]),
                        "low": number(row["low"]),
                        "close": number(row["close"]),
                        "volume": volume,
                        "parts": row.get("_display_seconds", base) // base,
                        "source": "realtime_bars"
                        if row.get("type") == "realtime_bar"
                        else "extended_history"
                        if row.get("history_scope") == "extended"
                        else "history",
                    }
                else:
                    bucket.update(
                        high=max(bucket["high"], number(row["high"])),
                        low=min(bucket["low"], number(row["low"])),
                        close=number(row["close"]),
                        volume=bucket["volume"] + volume
                        if bucket["volume"] is not None and volume is not None
                        else None,
                        parts=bucket["parts"] + row.get("_display_seconds", base) // base,
                    )
            end = max(
                (int(r["timestamp"]) + r.get("_display_seconds", base) for r in rows), default=0
            )
            for tick in list(self.buffered_ticks.get(conid, []))[-5000:]:
                if tick["timestamp"] < end or tick["timestamp"] >= boundary:
                    continue
                start = int(tick["timestamp"]) // seconds * seconds
                price, size = number(tick["price"]), number(tick["size"])
                bucket = buckets.get(start)
                if bucket is None:
                    buckets[start] = {
                        "timestamp": start,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": size,
                        "parts": None,
                        "source": "live_trades",
                    }
                else:
                    bucket.update(
                        high=max(bucket["high"], price),
                        low=min(bucket["low"], price),
                        close=price,
                        volume=bucket["volume"] + size if bucket["volume"] is not None else None,
                    )
            result[str(seconds)] = [
                {
                    **{
                        k: str(v)
                        if k in {"open", "high", "low", "close", "volume"} and v is not None
                        else v
                        for k, v in b.items()
                    },
                    "eligibility": "Display only; strategy uses validated live trades",
                    "complete": b["timestamp"] + seconds <= datetime.now(UTC).timestamp()
                    and (b["parts"] == seconds // base),
                    "timestamp": datetime.fromtimestamp(b["timestamp"], UTC).isoformat(),
                }
                for _, b in sorted(buckets.items())[-limit:]
            ]
        return result
