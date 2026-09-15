from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from test_strategy_run_service import (
    _dataset_registration,
    _draft_request,
    _risk_context,
    _service,
    _trades,
    _workflow_request,
)

from trading_oms_backend.strategy_run_service import StrategyRunError
from trading_oms_backend.typed_workflow_definitions import WorkflowDefinitionError
from trading_oms_backend.typed_workflow_dsl import WorkflowDslError, parse_workflow_dsl_document


def armed_service(root: Path):
    service, store = _service(root)
    request = _workflow_request()
    store.create_workflow(request)
    service.register_dataset(_dataset_registration(), _trades())
    service.create_draft(
        request.workflow_id, _draft_request(), requested_by="strategy-operator-001"
    )
    service.arm_run(
        "strategy-run-001",
        authorized_by="strategy-operator-001",
        authorized_at="2026-07-08T13:00:00Z",
        expires_at="2026-07-08T20:00:00Z",
    )
    return service


def test_unsupported_protective_stop_wiring_is_rejected_before_save() -> None:
    request = _workflow_request()
    for edge in request.document["edges"]:
        if edge["target_node"] == "protective-stop" and edge["target_port"] == "stop_price":
            edge["source_node"] = "opening-high"
    with pytest.raises(WorkflowDslError, match="supported breakout topology"):
        parse_workflow_dsl_document(request.document)


def test_interruption_before_completion_cannot_duplicate_fill_evidence(tmp_path: Path) -> None:
    service = armed_service(tmp_path)
    original = service._put_run

    def interrupted(record):
        if record.state == "completed":
            raise OSError("injected completion interruption")
        return original(record)

    with patch.object(service, "_put_run", side_effect=interrupted):
        with pytest.raises(OSError, match="interruption"):
            service.simulate_run("strategy-run-001", risk_context=_risk_context())
    before = service.journal_records()
    assert sum(e.event_type == "workflow.order.filled" for e in before) == 1
    restored, _ = _service(tmp_path)
    with pytest.raises(StrategyRunError, match="evidence unavailable"):
        restored.simulate_run("strategy-run-001", risk_context=_risk_context())
    assert restored.journal_records() == before


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_completed_run_requires_exact_journal_evidence(tmp_path: Path, damage: str) -> None:
    service = armed_service(tmp_path)
    service.simulate_run("strategy-run-001", risk_context=_risk_context())
    journal_path = tmp_path / "strategy-journal.jsonl"
    original = journal_path.read_text(encoding="utf-8")
    journal_path.write_text(
        "" if damage == "missing" else original.replace('"price":"101.05"', '"price":"101.06"'),
        encoding="utf-8",
    )
    assert journal_path.read_text(encoding="utf-8") != original
    restored, _ = _service(tmp_path)
    with pytest.raises(StrategyRunError, match="evidence unavailable"):
        restored.get_run("strategy-run-001")
    with pytest.raises(StrategyRunError, match="evidence unavailable"):
        restored.simulate_run("strategy-run-001", risk_context=_risk_context())


def test_typed_workflow_rejects_stale_expected_version(tmp_path: Path) -> None:
    _, store = _service(tmp_path)
    request = _workflow_request()
    store.create_workflow(request)
    updated = _workflow_request(requested_at="2026-07-08T12:01:00Z", expected_version=1)
    store.update_workflow(request.workflow_id, updated)
    stale = _workflow_request(requested_at="2026-07-08T12:02:00Z", expected_version=1)
    with pytest.raises(WorkflowDefinitionError, match="expected_version"):
        store.update_workflow(request.workflow_id, stale)


def test_independent_services_cannot_reserve_the_same_execution(tmp_path: Path) -> None:
    first = armed_service(tmp_path)
    second, _ = _service(tmp_path)
    first_snapshot = first.get_run("strategy-run-001")
    second_snapshot = second.get_run("strategy-run-001")
    first._reserve_execution(first_snapshot)
    with pytest.raises(StrategyRunError, match="evidence unavailable"):
        second._reserve_execution(second_snapshot)
    assert not any(e.event_type == "workflow.order.filled" for e in first.journal_records())


def test_concurrent_exact_requests_produce_only_one_fill(tmp_path: Path) -> None:
    service = armed_service(tmp_path)
    other, _ = _service(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(s.simulate_run, "strategy-run-001", risk_context=_risk_context())
            for s in (service, other)
        ]
        assert futures[0].result() == futures[1].result()
    assert sum(e.event_type == "workflow.order.filled" for e in service.journal_records()) == 1


@pytest.mark.parametrize("execution_time", ["2026-07-08T20:00:00Z", "2026-07-09T13:00:00Z"])
def test_expired_authorization_uses_execution_clock_when_time_is_omitted(
    tmp_path: Path, execution_time: str
) -> None:
    service = armed_service(tmp_path)
    service._clock = lambda: execution_time
    with pytest.raises(StrategyRunError, match="expired"):
        service.simulate_run("strategy-run-001", risk_context=_risk_context())
    assert not any(e.event_type == "workflow.order.filled" for e in service.journal_records())


def test_emergency_stop_survives_service_restart(tmp_path: Path) -> None:
    service = armed_service(tmp_path)
    service.set_emergency_state(
        active=True, actor="admin-operator-001", timestamp="2026-07-08T13:01:00Z"
    )
    restored, _ = _service(tmp_path)
    assert restored.get_run("strategy-run-001").state == "disarmed"
    with pytest.raises(StrategyRunError, match="emergency stop"):
        restored._ensure_emergency_allowed()
    restored.set_emergency_state(
        active=False, actor="admin-operator-001", timestamp="2026-07-08T13:02:00Z"
    )
    restored._ensure_emergency_allowed()
    assert restored.get_run("strategy-run-001").state == "disarmed"


def test_known_entry_fill_does_not_exceed_authorized_initial_stop_risk(tmp_path: Path) -> None:
    from decimal import Decimal

    service = armed_service(tmp_path)
    result = service.simulate_run("strategy-run-001", risk_context=_risk_context()).result
    assert result is not None
    actual_initial_risk = (
        Decimal(result.entry_fill_price) - Decimal(result.protective_stop_price)
    ) * Decimal(result.shares)
    assert actual_initial_risk <= Decimal("100.00")


@pytest.mark.parametrize("changed_field", ["risk_context", "reconciled"])
def test_completed_retry_requires_the_original_execution_request(
    tmp_path: Path, changed_field: str
) -> None:
    service = armed_service(tmp_path)
    original = service.simulate_run("strategy-run-001", risk_context=_risk_context())
    before = service.journal_records()
    restored, _ = _service(tmp_path)
    assert restored.simulate_run("strategy-run-001", risk_context=_risk_context()) == original
    risk_context = _risk_context()
    if changed_field == "risk_context":
        risk_context = replace(risk_context, buying_power="1.00")
    with pytest.raises(StrategyRunError, match="execution request differs"):
        restored.simulate_run(
            "strategy-run-001",
            risk_context=risk_context,
            reconciled=changed_field != "reconciled",
        )
    assert restored.journal_records() == before
