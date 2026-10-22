"""Execution-derived currency allocations. Virtual FX positions are never evidence."""

import json
from decimal import Decimal

from .graph import number


def executions(store):
    orders = {o["id"]: o for o in store.orders()}
    with store.connect() as db:
        rows = db.execute("SELECT * FROM executions ORDER BY rowid").fetchall()
    corrected = {}
    for row in rows:
        event = json.loads(row["payload"])
        parts = event["execution_id"].rsplit(".", 1)
        group, revision = (
            (parts[0], int(parts[1]))
            if len(parts) == 2 and parts[1].isdigit()
            else (event["execution_id"], 0)
        )
        if group not in corrected or revision > corrected[group][0]:
            corrected[group] = revision, orders[row["order_id"]], event
    return [(o, e) for _, o, e in corrected.values()]


def ledger(store):
    flows, runs, missing = {}, {}, []
    for order, event in executions(store):
        plan = order["payload"].get("fx_plan")
        if not plan:
            payload = order["payload"]
            currency = payload.get(
                "currency", (payload.get("stock_plan") or {}).get("currency", "USD")
            )
            scale = number((payload.get("stock_plan") or {}).get("rules", {}).get("price_scale", 1))
            sign = 1 if event["side"] == "BOT" else -1
            flows[currency] = (
                flows.get(currency, Decimal(0))
                - number(event["quantity"]) * number(event["price"]) * scale * sign
            )
            fee = store.get("commission", event["execution_id"])
            if fee:
                flows[fee["currency"]] = flows.get(fee["currency"], Decimal(0)) - number(
                    fee["amount"]
                )
            continue
        amount, price = number(event["quantity"]), number(event["price"])
        sign = 1 if event["side"] == "BOT" else -1
        key = order["run_id"]
        run = runs.setdefault(
            key,
            {
                "quantity": Decimal(0),
                "bought": Decimal(0),
                "cost": Decimal(0),
                "flows": {},
                "fees": {},
            },
        )
        if run["quantity"] == 0 and sign == 1:
            run["bought"], run["cost"] = Decimal(0), Decimal(0)
        run["quantity"] += amount * sign
        if sign == 1:
            run["bought"] += amount
            run["cost"] += amount * price
        for currency, change in (
            (plan["base_currency"], amount * sign),
            (plan["currency"], -amount * price * sign),
        ):
            run["flows"][currency] = run["flows"].get(currency, Decimal(0)) + change
            flows[currency] = flows.get(currency, Decimal(0)) + change
        fee = store.get("commission", event["execution_id"])
        if not fee:
            missing.append(event["execution_id"])
        else:
            currency, value = fee["currency"], number(fee["amount"])
            run["fees"][currency] = run["fees"].get(currency, Decimal(0)) + value
            flows[currency] = flows.get(currency, Decimal(0)) - value
    return {"flows": flows, "runs": runs, "missing_commissions": missing}


def serialized(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: serialized(v) for k, v in value.items()}
    return value
