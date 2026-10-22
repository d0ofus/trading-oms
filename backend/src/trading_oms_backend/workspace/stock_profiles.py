"""Additive stock profiles; original share-capped profiles remain immutable."""

from .qualification import DEFAULTS


def stock_profiles(store):
    if not store.get("risk_profile", "stock_smoke:1"):
        store.backup(store.directory / "backups")
        with store.transaction() as db:
            for original in DEFAULTS:
                profile = {
                    **original,
                    "id": "stock_" + original["id"],
                    "name": "Stock qualification — one legal lot"
                    if original["id"] == "smoke"
                    else "Qualified stock risk limits",
                    "stock_units": 1 if original["id"] == "smoke" else None,
                }
                store.write(db, "risk_profile", profile["id"] + ":1", profile)
                store.append(db, "risk_profile.stock.published", profile)
    if not store.get("risk_profile", "stock_selected:2"):
        store.backup(store.directory / "backups")
        with store.transaction() as db:
            for identity, name, units, runs in (
                ("stock_selected", "Paper stock — selected quantity", None, 5),
                ("stock_one_lot", "Paper stock — one-lot qualification", 1, 1),
            ):
                profile = {
                    "id": identity,
                    "version": 2,
                    "name": name,
                    "stock_units": units,
                    "runs": runs,
                    "notional": None,
                    "planned_stop_risk": None,
                    "entry_timeout": 30,
                    "risk_policy": "paper_stock_v2",
                }
                store.write(db, "risk_profile", identity + ":2", profile)
                store.append(db, "risk_profile.stock.published", profile)
    return store.list("risk_profile")
