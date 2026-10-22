"""New stock policy must not reinterpret legacy graphs or permit unfunded orders."""

import copy
from decimal import Decimal

import pytest
from test_workspace_stock_policy import contract

from trading_oms_backend.workspace.graph import compile_graph
from trading_oms_backend.workspace.stock_policy import size_stock
from trading_oms_backend.workspace.stock_strategies import stock_templates


@pytest.mark.parametrize("index", range(4))
def test_schema_eight_preserves_nodes_edges_and_calculations(index):
    old = stock_templates()[index]["document"]
    original = compile_graph(old)
    new = copy.deepcopy(old)
    new["schema_version"] = 8
    new["settings"].update(notional=None, risk=None, sizing="fixed")
    graph = compile_graph(new)
    assert graph.document["nodes"] == original.document["nodes"]
    assert graph.document["edges"] == original.document["edges"]
    assert compile_graph(old).digest == original.digest
    inputs = {key: Decimal("100") for key in original.inputs}
    assert graph.evaluate(inputs, {}) == original.evaluate(inputs, {})


def test_new_templates_have_optional_limits_and_explicit_quantity():
    for template in stock_templates(8):
        settings = template["document"]["settings"]
        assert settings["notional"] is settings["risk"] is None
        assert settings["sizing"] == "fixed"
    assert stock_templates()[-1]["document"]["settings"]["notional"] == "25"


def test_risk_sizing_requires_a_positive_budget():
    document = stock_templates(8)[0]["document"]
    document["settings"]["sizing"] = "risk"
    with pytest.raises(ValueError, match="risk.*budget|stop-risk"):
        compile_graph(document)


def usd_contract():
    c = contract()
    c.update(currency="USD", routing_exchange="SMART", primary_exchange="ARCA")
    c["stock_rules"].update(
        currency="USD",
        calendar="XNYS",
        minimum_quantity="1",
        quantity_increment="1",
        fee_reserve="1",
    )
    return c


def test_new_policy_exceeds_former_caps_and_records_actual_risk():
    settings = {"notional": None, "risk": None, "shares": "200", "sizing": "fixed"}
    profile = {"notional": None, "planned_stop_risk": None, "stock_units": None}
    quantity, reserve = size_stock(
        settings,
        profile,
        usd_contract(),
        [(Decimal(100), Decimal(99))],
        Decimal(1),
        Decimal(100000),
        Decimal(100000),
        policy="paper_stock_v2",
    )
    assert quantity == 200
    assert Decimal(reserve["notional"]) == 20000
    assert Decimal(reserve["risk"]) == 200
    assert reserve["risk_policy"] == "paper_stock_v2"


@pytest.mark.parametrize("funds,cap", [("100", None), ("100000", "1000")])
def test_explicit_quantity_is_rejected_instead_of_silently_reduced(funds, cap):
    with pytest.raises(ValueError, match="quantity|fund|ceiling"):
        size_stock(
            {"notional": cap, "risk": None, "shares": "200", "sizing": "fixed"},
            {"notional": None, "planned_stop_risk": None, "stock_units": None},
            usd_contract(),
            [(Decimal(100), Decimal(99))],
            Decimal(1),
            Decimal(funds),
            Decimal(funds),
            policy="paper_stock_v2",
        )


def test_legacy_sizing_still_enforces_original_caps():
    quantity, _ = size_stock(
        {"notional": "1000", "risk": "10", "shares": "200", "sizing": "fixed"},
        {"notional": "1000", "planned_stop_risk": "10", "stock_units": None},
        usd_contract(),
        [(Decimal(100), Decimal(99))],
        Decimal(1),
        Decimal(100000),
        Decimal(100000),
    )
    assert quantity == 10


def test_funded_stock_order_crosses_all_previous_caps_without_qualification(tmp_path, monkeypatch):
    from test_workspace_stock_execution import enter, fixture

    from trading_oms_backend.workspace.stock_profiles import stock_profiles
    from trading_oms_backend.workspace.store import now

    e, old, _ = fixture(tmp_path, monkeypatch)
    e.disarm(old["id"])
    document = stock_templates(8)[-1]["document"]
    draft = e.store.save_draft(None, "Explicit paper quantity", document, 0)
    e.store.publish(draft["id"], draft["revision"])
    sizing = {"shares": "2000", "notional": None, "risk": None, "sizing": "fixed"}
    plan = e.stock_compatibility(draft["id"], 1, old["conid"], sizing=sizing)
    assert plan["can_prepare"]
    run = e.create_run(
        draft["id"], 1, old["conid"], sizing=sizing, execution_plan_revision=plan["plan"]["hash"]
    )
    from trading_oms_backend.workspace.store import Conflict

    preview = e.arm_preview([run["id"]])
    assert preview["limits"]["id"] == "stock_selected"
    assert preview["resume_policy"] == "same_engine_routine_v1"
    with pytest.raises(Conflict, match="Reviewed decisions changed"):
        e.arm([run["id"]], "old-client-without-terms")
    e.quotes[old["conid"]]["ask"]["received_at"] = now()
    assert e.arm_preview([run["id"]])["review_fingerprint"] == preview["review_fingerprint"]
    stock_profiles(e.store)
    run.update(
        armed=True,
        expires_at=old["expires_at"],
        authorized_at=old["authorized_at"],
        authorization_id="fixture",
        limits=e.store.get("risk_profile", "stock_selected:2"),
    )
    e.store.put("run", run["id"], run)
    e.facts.update(AvailableFunds="100000", GrossPositionValue="10000")
    for tag in ("CashBalance", "SettledCash"):
        e.currency_facts[(tag, "HKD")] = {"value": "1000000", "received_at": now()}
    order = enter(e, run)
    reservation = e.store.get("reservation", order["id"])
    assert order["payload"]["quantity"] == "2000"
    assert Decimal(reservation["notional"]) > 5000
    assert Decimal(reservation["risk"]) > 50
    assert len(e.broker.submitted) == 1
    from types import SimpleNamespace

    from trading_oms_backend.workspace.broker import PaperGateway

    gateway = PaperGateway(e.observations)
    calls = []
    gateway.client = SimpleNamespace(
        isConnected=lambda: True, placeOrder=lambda *args: calls.append(args)
    )
    gateway._accounts = [
        "DU0000000"
    ]  # Synthetic adapter fixture, never a configured broker account.
    gateway._attested = True
    gateway._contracts[run["conid"]] = SimpleNamespace(
        conId=run["conid"], secType="STK", currency="HKD", exchange="SEHK"
    )
    intent = {**order["payload"], **order}
    gateway.submit_bracket(intent)
    assert calls[0][2].totalQuantity == Decimal(2000)
    with pytest.raises(ValueError, match="approved quantity"):
        gateway.submit_bracket({**intent, "quantity": "2200"})
    # Actual partial executions retain protection without nullable-limit errors.
    from test_workspace_stock_execution import fill, observation

    observation(e, order, "Submitted", filled="1000")
    observation(e, order, "Submitted", child=True)
    fill(e, order, quantity="1000")
    e._finish_reconcile()
    assert e.owned()[run["id"]]["quantity"] == 1000
    protection = e.store.get("stock_protection", run["id"])
    assert protection["quantity"] == "1000"
    assert protection["stop"] == "29.80"
    assert not any(i["code"] == "risk_gap" for i in e.incidents.open())
    current = e.arm_preview([run["id"]])["review_fingerprint"]
    e.incident("order_uncertain", "Synthetic uncertain order")
    assert e.arm_preview([run["id"]])["review_fingerprint"] != current
