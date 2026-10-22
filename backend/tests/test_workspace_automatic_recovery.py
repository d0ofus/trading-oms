import pytest
from test_workspace_health import healthy_watchdog
from test_workspace_incidents import recovered_engine


def advance(e, clock, seconds=35):
    e.reconciliation_evidence["started_sequence"] = e.incidents.watermark()
    e.refresh_incidents()
    for _ in range(seconds // 5):
        clock[0] += 5
        e.last_loop = e.reconciled_at = clock[0]
        healthy_watchdog(e)
        e.refresh_incidents()


def test_verified_watchdog_releases_without_arming_or_clearing_emergency(tmp_path, monkeypatch):
    e, item, _ = recovered_engine(tmp_path, monkeypatch, automatic=True)
    released = e.incidents.get(item["id"])
    assert released["restriction"] == "released"
    assert released["release_actor"] == "automatic-recovery"
    assert released["release_policy"] == "automatic"
    assert not e.broker.submitted


@pytest.mark.parametrize(
    "code", ["engine_fault", "order_uncertain", "broker_201", "account_context"]
)
def test_dedicated_failures_still_need_operator(tmp_path, monkeypatch, code):
    e, item, _ = recovered_engine(tmp_path, monkeypatch, code, automatic=True)
    assert e.incidents.get(item["id"])["restriction"] == (
        "released" if code == "account_context" else "ready_for_release"
    )


def test_old_inactive_feed_retires_without_claiming_it_is_healthy(tmp_path, monkeypatch):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    item = e.incidents.raise_incident("trade_feed_failure", "Old feed", "old", conid=12)
    e.store.put("subscription", "12", {"conid": 12, "active": False})
    advance(e, clock)
    result = e.incidents.get(item["id"])
    assert result["restriction"] == "released"
    assert result["condition"] != "recovered"
    assert result["release_kind"] == "dependency_retired"
    assert not e.data.get(12)


@pytest.mark.parametrize("dependency", ["subscription", "run", "reservation", "position", "exit"])
def test_dependency_prevents_feed_retirement(tmp_path, monkeypatch, dependency):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    item = e.incidents.raise_incident("trade_feed_failure", "Feed", "old", conid=12)
    e.store.put("subscription", "12", {"conid": 12, "active": dependency == "subscription"})
    if dependency in {"run", "position", "exit"}:
        e.store.put(
            "run",
            "r",
            {
                "id": "r",
                "conid": 12,
                "archived": dependency != "run",
                "position": 1 if dependency == "position" else 0,
                "armed": dependency == "run",
            },
        )
    if dependency == "reservation":
        e.store.put("reservation", "x", {"conid": 12, "active": True})
    if dependency == "exit":
        e.store.put("exit_request", "r", {"run_id": "r"})
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "held"


def test_ownership_change_prevents_automatic_release(tmp_path, monkeypatch):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    item = e.incidents.raise_incident("watchdog", "New fault", e.process_identity)
    e.store.put("workspace", "engine_owner", {"instance": "different", "state": "running"})
    e.reconciliation_evidence["started_sequence"] = e.incidents.watermark()
    e.refresh_incidents()
    for _ in range(7):
        clock[0] += 5
        e.last_loop = e.reconciled_at = clock[0]
        e.refresh_incidents()
    assert e.incidents.get(item["id"])["restriction"] != "released"


def test_current_farm_requires_matching_recovery_but_new_connection_can_requalify(
    tmp_path, monkeypatch
):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    failure = {"source": "ibkr_service", "code": 2103, "farm": "usfarm.nj"}
    event = {"type": "broker_error", "request": -1, "code": 2103, "service": failure}
    e.observe(event)
    item = next(i for i in e.incidents.open() if i["code"] == "broker_2103")
    e.observe(event)
    assert e.incidents.get(item["id"])["occurrences"] == 1
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "held"
    e.broker.epoch += 1
    e.reconciliation_evidence["epoch"] = e.broker.epoch
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "released"


@pytest.mark.parametrize("code", ["connectivity", "broker_2110", "broker_2103"])
@pytest.mark.parametrize("required", [False, True])
def test_only_required_history_blocks_recovery_in_new_connection(
    tmp_path, monkeypatch, code, required
):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    item = e.incidents.raise_incident(code, "Old service", "previous-engine")
    e.store.put("subscription", "12", {"conid": 12, "active": True})
    e.data[12] = {"warm": False, "live": True, "subscription_status": "subscribed"}
    if required:
        e._preparation_dependencies = {12: {"conid": 12}}
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == ("held" if required else "released")
    e.data[12]["warm"] = True
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "released"


def test_broad_recovery_retains_failed_contract_restriction(tmp_path, monkeypatch):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    shared = e.incidents.raise_incident("connectivity", "Previous connection", "old")
    e.data[12] = {"warm": False, "live": True, "subscription_status": "subscribed"}
    e.store.put("subscription", "12", {"conid": 12, "active": True})
    for state in e.components_for(12).values():
        state["status"] = "healthy"
    e.components_for(12)["trade"]["status"] = "failed"
    advance(e, clock)
    assert e.incidents.get(shared["id"])["restriction"] == "released"
    holds = e.incidents.applicable([{"conid": 12}])
    assert len(holds) == 1 and holds[0]["code"] == "trade_feed_failure"
    assert not e.incidents.applicable([{"conid": 13}])


def test_unresolved_order_without_run_prevents_retirement(tmp_path, monkeypatch):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    item = e.incidents.raise_incident("trade_feed_failure", "Old feed", "old", conid=12)
    e.store.put("subscription", "12", {"conid": 12, "active": False})
    with e.store.transaction() as db:
        db.execute(
            "INSERT INTO outbox(id,run_id,hash,state,payload,created_at,broker_id) "
            "VALUES(?,?,?,?,?,?,?)",
            ("unknown", "missing-run", "fixture-hash", "unknown", '{"conid":12}', "fixture", 1),
        )
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "held"


def test_saved_twelve_episode_pattern_releases_only_current_verified_routine_risk(
    tmp_path, monkeypatch
):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    e.store.set_emergency(True)
    feed_items = []
    for conid in (12, 13):
        e.store.put("subscription", str(conid), {"conid": conid, "active": False})
        for code in (
            "quote_feed_failure",
            "trade_feed_failure",
            "history_feed_failure",
            "history_timeout",
        ):
            feed_items.append(
                e.incidents.raise_incident(code, "Saved feed", "previous", conid=conid)
            )
    service_items = [
        e.incidents.raise_incident(code, "Saved service", "previous", correlation_key=f"farm-{i}")
        for i, code in enumerate(("broker_2103", "broker_2103", "broker_2105", "broker_2110"))
    ]
    uncertain = e.incidents.raise_incident("order_uncertain", "Uncertain order", "previous")
    e.refresh_incidents()
    # Current complete ownership evidence retires unused feeds immediately;
    # actual service recovery still needs reconciliation after its failure.
    assert all(e.incidents.get(i["id"])["restriction"] == "released" for i in feed_items)
    assert all(e.incidents.get(i["id"])["restriction"] != "released" for i in service_items)
    advance(e, clock)
    assert all(e.incidents.get(i["id"])["release_kind"] == "dependency_retired" for i in feed_items)
    assert all(
        e.incidents.get(i["id"])["release_kind"] == "verified_recovery" for i in service_items
    )
    assert e.incidents.get(uncertain["id"])["restriction"] != "released"
    assert e.store.emergency()
    assert not e.broker.submitted


def test_known_service_without_farm_uses_code_and_current_dependency_evidence(
    tmp_path, monkeypatch
):
    e, _, clock = recovered_engine(tmp_path, monkeypatch, automatic=True)
    e.observe({"type": "broker_error", "request": -1, "code": 2105})
    item = next(i for i in e.incidents.open() if i["code"] == "broker_2105")
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "held"
    e.observe({"type": "broker_error", "request": -1, "code": 2106})
    advance(e, clock)
    assert e.incidents.get(item["id"])["restriction"] == "released"
