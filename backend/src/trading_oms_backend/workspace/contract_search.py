"""Bounded, connection-scoped contract discovery, separate from execution feeds."""

import time
import uuid


class ContractSearch:
    def resolve(self, symbol="", **filters):
        filters = {k: v for k, v in filters.items() if v not in (None, "")}
        symbol = symbol.strip().upper()
        request = self.broker.resolve(symbol, **filters)
        if not hasattr(self, "_searches"):
            self._searches = {}
        identity = uuid.uuid4().hex
        self._searches[identity] = {
            "search_id": identity,
            "request": request,
            "epoch": self.broker.epoch,
            "query": {"symbol": symbol, **filters},
            "state": "searching",
            "results": [],
            "detail": "Searching IBKR contract details…",
            "started": time.monotonic(),
            "truncated": False,
        }
        while len(self._searches) > 20:
            expired = self._searches.pop(next(iter(self._searches)))
            retained = {r["conid"] for s in self._searches.values() for r in s["results"]}
            retained.update(self.data)
            retained.update(r.get("conid") for r in self.store.list("run"))
            retained.update(s["query"].get("conid") for s in self._searches.values())
            discarded = []
            for result in expired["results"]:
                if result["conid"] not in retained:
                    self.contracts.pop(result["conid"], None)
                    discarded.append(result["conid"])
            if hasattr(self.broker, "retire_search"):
                self.broker.retire_search(expired["request"], discarded)
        return self.search_status(identity)

    def search_status(self, identity):
        item = getattr(self, "_searches", {}).get(identity)
        if not item:
            raise ValueError("Contract search expired. Start a new search.")
        if item["state"] == "searching":
            if not self.connected or item["epoch"] != self.broker.epoch:
                item.update(
                    state="interrupted", detail="Connection changed. Reconnect and search again."
                )
            elif time.monotonic() - item["started"] >= 30:
                item.update(
                    state="timed_out",
                    detail="Search timed out after 30 seconds. Check route and connection; retry.",
                )
        return {k: v for k, v in item.items() if k != "started"}

    def search_observed(self, event):
        """Return False to fence obsolete or invalid search observations."""
        kind = event["type"]
        if kind not in {
            "contract",
            "contract_candidate",
            "contracts_end",
            "contracts_truncated",
            "broker_error",
        }:
            return True
        if event.get("epoch", self.broker.epoch) != self.broker.epoch:
            return False
        if kind == "broker_error" and event.get("context") not in {"search", "retired_search"}:
            return True  # Order IDs and data request IDs occupy distinct broker namespaces.
        if kind == "broker_error" and event["code"] in {
            1100,
            1101,
            1102,
            1300,
            502,
            504,
            2104,
            2106,
            2107,
            2108,
            2158,
            2109,
            2119,
        }:
            # Request correlation must never swallow shared connectivity handling.
            if event["code"] in {1100, 1101, 1102, 1300, 502, 504}:
                for search in getattr(self, "_searches", {}).values():
                    if search["state"] == "searching":
                        search.update(
                            state="interrupted",
                            detail="Connection interrupted. Reconnect and search again.",
                        )
            return True
        request = event.get("request")
        items = getattr(self, "_searches", {})
        item = next(
            (
                i
                for i in items.values()
                if i["request"] == request and i["epoch"] == self.broker.epoch
            ),
            None,
        )
        if not item:
            return event.get("context") not in {"search", "retired_search"}
        if self.search_status(item["search_id"])["state"] != "searching":
            return False
        if kind == "contracts_truncated":
            item["truncated"] = True
            return False
        if kind == "broker_error":
            code = event["code"]
            explanation = (
                "No matching or ambiguous contract. Check ID, routing exchange and filters."
                if code == 200
                else "Contract discovery failed. Check connection, filters and API availability."
            )
            item.update(state="failed", code=code, detail=f"IBKR code {code}: {explanation}")
            self.store.event(
                "contract.search.failed",
                {"search_id": item["search_id"], "code": code, "request": request},
            )
            return False
        if kind == "contracts_end":
            count = len(item["results"])
            item.update(
                state="results" if count else "empty",
                detail=f"{count} contract results."
                if count
                else "No contracts matched these filters.",
            )
            return False
        query = item["query"]
        if kind == "contract" and query.get("conid"):
            mismatched = (
                query["conid"] != event.get("conid")
                or any(query.get(k) and query[k] != event.get(k) for k in ("sec_type", "currency"))
                or (
                    query.get("symbol")
                    and query["symbol"] not in {event.get("symbol"), event.get("local_symbol")}
                )
            )
            route = query.get("exchange")
            valid = event.get("valid_exchanges", [])
            if mismatched or (route and route != event.get("exchange") and route not in valid):
                item.update(
                    state="failed",
                    detail="Returned contract identity or route differs from the supplied filters.",
                )
                return False
        if len(item["results"]) >= 200:
            item["truncated"] = True
            return False
        result = {k: v for k, v in event.items() if k not in {"type", "epoch", "request"}}
        if kind == "contract" and query.get("exchange"):
            result["routing_exchange"] = query["exchange"]
        if not any(
            r["conid"] == result["conid"] and r.get("exchange") == result.get("exchange")
            for r in item["results"]
        ):
            item["results"].append(result)
        if kind == "contract_candidate":
            # Candidates belong to this search, not the resolved-contract cache.
            return False
        # A newer search for this contract owns the current projection.
        newer = [i for i in items.values() if i["request"] > request]
        return not any(any(r["conid"] == result["conid"] for r in i["results"]) for i in newer)
