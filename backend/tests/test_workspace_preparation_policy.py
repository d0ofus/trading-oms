from datetime import UTC, datetime

from test_workspace_stock_policy import contract

from trading_oms_backend.workspace.stock_policy import compatibility
from trading_oms_backend.workspace.stock_rules import resolve_rules
from trading_oms_backend.workspace.stock_sessions import StockSession
from trading_oms_backend.workspace.stock_strategies import stock_templates


def meta():
    c = contract()
    c.pop("stock_rules")
    c.update(
        conid=107113386,
        symbol="META",
        currency="USD",
        primary_exchange="NASDAQ",
        routing_exchange="NASDAQ",
        min_size="0.0001",
        size_increment="0.0001",
        price_magnifier=1,
        time_zone="US/Eastern",
        trading_hours="20260922:0400-20260922:2000",
        liquid_hours="20260922:0930-20260922:1600",
        order_types=["LMT", "MKT", "STP", "GTD"],
    )
    return c


def test_auto_us_rules_use_whole_shares_provenance_and_automatic_fee_policy():
    c = meta()
    rules, evidence = resolve_rules(c, None)
    assert rules["minimum_quantity"] == rules["quantity_increment"] == "1"
    assert rules["fee_reserve"] == "2.00"
    assert rules["source"] != "operator_verified"
    assert not rules["fractional_protection"]
    assert evidence["minimum_quantity"]["route"] == "NASDAQ"
    rules, _ = resolve_rules(c, {"amount": "1", "revision": 2})
    assert rules["fee_reserve"] == "2.00"  # Legacy override cannot change the automatic policy.
    c["stock_rules"] = rules
    result = compatibility(c, stock_templates()[-1]["document"])
    assert not result["blockers"]


def test_unknown_hk_rules_not_invented():
    c = contract()
    c.pop("stock_rules")
    assert resolve_rules(c, None)[0] is None


def test_premarket_is_separate_policy_with_open_boundary_and_no_postmarket():
    c = meta()
    c["stock_rules"] = resolve_rules(c, {"amount": "1", "revision": 1})[0]
    regular = StockSession(c)
    extended = StockSession(c, "premarket_regular")
    pre = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    assert not regular.tradable(pre)
    assert extended.tradable(pre)
    assert extended.interval_start(datetime(2026, 9, 22, 13, 30, tzinfo=UTC)).hour == 13
    assert not extended.tradable(datetime(2026, 9, 22, 20, 0, tzinfo=UTC))
    plan = compatibility(
        c, stock_templates()[-1]["document"], "locally_monitored", "premarket_regular"
    )
    assert not plan["blockers"]
    assert plan["plan"]["entry_type"] == "LMT"
    assert compatibility(
        c, stock_templates()[2]["document"], "locally_monitored", "premarket_regular"
    )["blockers"]
