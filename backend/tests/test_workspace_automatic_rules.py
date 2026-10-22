from datetime import UTC, datetime

from test_workspace_preparation_policy import meta
from test_workspace_stock_policy import contract

from trading_oms_backend.workspace.stock_fees import fee_reserve
from trading_oms_backend.workspace.stock_rules import resolve_rules


def cache_reference(engine):
    from trading_oms_backend.workspace.stock_references import reference_day

    engine.store.put(
        "stock_reference",
        "HKEX",
        {
            "business_date": reference_day(),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "source": "Synthetic reference",
            "revision": "fixture",
            "rows": {"1810": {"symbol": "1810", "currency": "HKD", "board_lot": "200"}},
        },
    )


def hk():
    c = contract()
    c.pop("stock_rules")
    c.update(min_size="200", size_increment="200", price_magnifier=1, time_zone="Hongkong")
    c["reference_data"] = {
        "status": "ready",
        "business_date": datetime.now(UTC).date().isoformat(),
        "board_lot": "200",
        "currency": "HKD",
        "symbol": "1810",
        "source": "HKEX securities list",
        "revision": "fixture",
    }
    return c


def test_hk_metadata_automatically_derives_board_lot_without_manual_claims():
    rules, evidence = resolve_rules(hk(), None)
    assert rules["minimum_quantity"] == rules["quantity_increment"] == "200"
    assert rules["exit_increment"] == "200"
    assert rules["calendar"] == "XHKG"
    assert rules["source"] != "operator_verified"
    assert rules["fee_reserve"] != ""
    assert evidence["minimum_quantity"]["source"] == "ibkr_contract"


def test_us_rules_have_an_automatic_funding_allowance():
    rules, _ = resolve_rules(meta(), None)
    assert rules["minimum_quantity"] == "1"
    assert rules["fee_reserve"] != ""


def test_hk_conflicting_or_unavailable_lot_reference_is_not_guessed():
    for lot in (None, "100"):
        c = hk()
        c["reference_data"]["board_lot"] = lot
        assert resolve_rules(c, None)[0] is None


def test_fee_estimate_includes_round_trip_hk_stamp_and_external_fees():
    assert fee_reserve("HKD", 200, 6000) > 48  # 2 x (18 commission + 6 stamp), plus fees.
    assert fee_reserve("HKD", 200, 6000) < 52
    assert fee_reserve("USD", 1, 600) >= 2


def automatic_run(tmp_path, monkeypatch):
    from test_workspace_stock_execution import fixture

    e, run, published = fixture(tmp_path, monkeypatch)
    monkeypatch.delattr(e, "_resolve_stock_rules")
    c = e.contracts[run["conid"]]
    c.update(hk())
    cache_reference(e)
    c.update(
        metadata_instance=e.process_identity,
        metadata_epoch=e.broker.epoch,
        liquid_hours=datetime.now(UTC).strftime("%Y%m%d") + ":0930-1600",
    )
    e.observe(
        {
            "type": "market_rule",
            "rule": c["market_rule"],
            "increments": e.market_rules[c["market_rule"]],
        }
    )
    e._resolve_stock_rules(c["conid"], automatic=True)
    result = e.stock_compatibility(published["strategy_id"], 1, c["conid"])
    assert not result["blockers"]
    run["binding"] = e._stock_binding(
        published, c["conid"], None, "broker_held", result["plan"]["hash"]
    )
    e.store.put("run", run["id"], run)
    return e, run, published


def test_automatic_board_lot_entry_preserves_risk_and_paper_routing(tmp_path, monkeypatch):
    from test_workspace_stock_execution import enter

    e, run, _ = automatic_run(tmp_path, monkeypatch)
    order = enter(e, run)
    assert order["payload"]["quantity"] == "200"
    assert order["payload"]["stock_plan"]["rules"]["exit_increment"] == "200"
    assert order["payload"]["stock_plan"]["routing_exchange"] == "SEHK"
    assert len(e.broker.submitted) == 1


def test_minimum_lot_budget_conflict_reports_native_and_usd_without_mutation(tmp_path, monkeypatch):
    e, run, p = automatic_run(tmp_path, monkeypatch)
    result = e.stock_compatibility(p["strategy_id"], 1, run["conid"], sizing={"notional": "25"})
    assert not result["can_prepare"]
    assert result["minimum_lot"]["native_notional"] == "6000"
    assert result["resolution_status"] == "budget_requirement"
    assert not e.broker.submitted


def test_actual_fill_reserves_automatic_fees_for_its_actual_notional(tmp_path, monkeypatch):
    from test_workspace_stock_execution import enter, fill, observation

    from trading_oms_backend.workspace.graph import number

    e, run, _ = automatic_run(tmp_path, monkeypatch)
    entry = enter(e, run)
    observation(e, entry)
    fill(e, entry, price="40")
    reservation = e.store.get("reservation", entry["id"])
    assert number(reservation["native_funds"]) >= 8000 + fee_reserve("HKD", 200, 8000)


def test_legacy_rule_endpoint_cannot_override_automatic_binding(tmp_path, monkeypatch):
    import copy

    e, run, _ = automatic_run(tmp_path, monkeypatch)
    old = copy.deepcopy(e.contracts[run["conid"]]["stock_rules"])
    manual = contract()["stock_rules"]
    manual["quantity_increment"] = manual["minimum_quantity"] = "1"
    e.stock_rules(run["conid"], manual)
    assert e.contracts[run["conid"]]["stock_rules"] == old
    assert e._binding_valid(run)


def test_automatic_preparation_does_not_replace_existing_legacy_binding(tmp_path, monkeypatch):
    from test_workspace_stock_execution import fixture

    e, run, p = fixture(tmp_path, monkeypatch)
    e.store.put("stock_rules", str(run["conid"]), e.contracts[run["conid"]]["stock_rules"])
    monkeypatch.delattr(e, "_resolve_stock_rules")
    cache_reference(e)
    e.contracts[run["conid"]].update(
        min_size="200", size_increment="200", reference_data=hk()["reference_data"]
    )
    e.stock_compatibility(p["strategy_id"], 1, run["conid"])
    assert e._binding_valid(run)
    assert run["binding"]["execution_plan"]["rules"]["exit_increment"] == "1"


def test_stale_reference_rejects_cached_contract_claim_and_blocks_authorization(
    tmp_path, monkeypatch
):
    e, run, p = automatic_run(tmp_path, monkeypatch)
    reference = e.store.get("stock_reference", "HKEX")
    reference["business_date"] = "2000-01-01"
    e.store.put("stock_reference", "HKEX", reference)
    result = e.stock_compatibility(p["strategy_id"], 1, run["conid"])
    assert not result["can_prepare"]
    assert result["resolution_status"] == "checking"
    assert not e._stock_checks(run)[0]["passed"]


def test_price_rules_from_previous_connection_cannot_authorize_new_automatic_entries(
    tmp_path, monkeypatch
):
    e, run, _ = automatic_run(tmp_path, monkeypatch)
    assert e.stock_metadata_ready(run["conid"])
    e.broker.epoch += 1
    e.contracts[run["conid"]]["metadata_epoch"] = e.broker.epoch
    assert not e.stock_metadata_ready(run["conid"])


def test_parser_reads_official_columns_and_rejects_missing_date():
    import io
    import zipfile

    import pytest

    from trading_oms_backend.workspace.stock_references import parse_hkex

    def workbook(date):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr(
                "xl/sharedStrings.xml",
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>'
                + date
                + "</t></si><si><t>Equity</t></si><si><t>HKD</t></si></sst>",
            )
            z.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row><c r="A1" t="s"><v>0</v></c></row><row>'
                '<c r="A4"><v>01810</v></c><c r="C4" t="s"><v>1</v></c>'
                '<c r="E4"><v>200</v></c><c r="Q4" t="s"><v>2</v></c>'
                "</row></sheetData></worksheet>",
            )
        return data.getvalue()

    result = parse_hkex(workbook("Updated as at 23/09/2026"))
    assert result["rows"]["1810"]["board_lot"] == "200"
    assert result["business_date"] == "2026-09-23"
    with pytest.raises(ValueError):
        parse_hkex(workbook("Invalid date"))
