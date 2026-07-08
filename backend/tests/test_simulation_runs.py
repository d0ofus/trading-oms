from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.simulation_runs import (
    SimulationRunBook,
    SimulationRunCreateRequest,
    SimulationRunError,
    SimulationRunTransitionRequest,
)

FORBIDDEN_PAYLOAD_KEYS = {
    "account",
    "account_id",
    "api_key",
    "authorization",
    "broker_host",
    "broker_port",
    "certificate",
    "connect_url",
    "credential",
    "host",
    "password",
    "place_order_url",
    "port",
    "private_key",
    "route",
    "secret",
    "socket",
    "submit_url",
    "token",
    "transmit",
    "transmit_url",
}


def test_simulation_run_book_creates_run_and_journals_it(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)

    run = book.create_run(
        SimulationRunCreateRequest(
            run_id="sim-run-001",
            requested_at="2026-07-08T00:00:00Z",
            replay_input_reference="fixtures/replay/aapl-session.jsonl",
        ),
    )

    assert run.to_json_dict() == {
        "schema_version": 1,
        "run_id": "sim-run-001",
        "status": "created",
        "created_at": "2026-07-08T00:00:00Z",
        "updated_at": "2026-07-08T00:00:00Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
        "journal_references": ["journal_sequence:1"],
    }

    records = journal.read_all()
    assert len(records) == 1
    assert records[0].event_type == "simulation_run.created"
    assert records[0].payload == {
        "schema_version": 1,
        "run_id": "sim-run-001",
        "status": "created",
        "requested_at": "2026-07-08T00:00:00Z",
        "replay_input_reference": "fixtures/replay/aapl-session.jsonl",
    }


def test_simulation_run_book_applies_valid_lifecycle_transitions(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)
    book.create_run(_create_request())

    running = book.transition_run(
        SimulationRunTransitionRequest(
            transition_id="transition-001",
            run_id="sim-run-001",
            status="running",
            occurred_at="2026-07-08T00:01:00Z",
            reason="replay_loaded",
        ),
    )
    completed = book.transition_run(
        SimulationRunTransitionRequest(
            transition_id="transition-002",
            run_id="sim-run-001",
            status="completed",
            occurred_at="2026-07-08T00:02:00Z",
            reason="deterministic_replay_finished",
        ),
    )

    assert running.status == "running"
    assert running.journal_references == ("journal_sequence:1", "journal_sequence:2")
    assert completed.status == "completed"
    assert completed.updated_at == "2026-07-08T00:02:00Z"
    assert completed.journal_references == (
        "journal_sequence:1",
        "journal_sequence:2",
        "journal_sequence:3",
    )

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        "simulation_run.created",
        "simulation_run.status_changed",
        "simulation_run.status_changed",
    ]
    assert records[2].payload["previous_status"] == "running"
    assert records[2].payload["status"] == "completed"


def test_simulation_run_create_is_idempotent_for_same_payload_without_new_journal_record(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)

    first = book.create_run(_create_request())
    second = book.create_run(_create_request())

    assert second == first
    assert len(journal.read_all()) == 1


def test_simulation_run_create_rejects_conflicting_duplicate_run_id(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)
    book.create_run(_create_request())

    with pytest.raises(SimulationRunError, match="conflicting duplicate run_id"):
        book.create_run(
            SimulationRunCreateRequest(
                run_id="sim-run-001",
                requested_at="2026-07-08T00:00:00Z",
                replay_input_reference="fixtures/replay/msft-session.jsonl",
            ),
        )

    assert len(journal.read_all()) == 1


def test_transition_id_is_idempotent_for_same_payload_without_new_journal_record(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)
    book.create_run(_create_request())
    transition = SimulationRunTransitionRequest(
        transition_id="transition-001",
        run_id="sim-run-001",
        status="running",
        occurred_at="2026-07-08T00:01:00Z",
        reason="replay_loaded",
    )

    first = book.transition_run(transition)
    second = book.transition_run(transition)

    assert second == first
    assert len(journal.read_all()) == 2


def test_transition_id_rejects_conflicting_duplicate_payload(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)
    book.create_run(_create_request())
    book.transition_run(
        SimulationRunTransitionRequest(
            transition_id="transition-001",
            run_id="sim-run-001",
            status="running",
            occurred_at="2026-07-08T00:01:00Z",
            reason="replay_loaded",
        ),
    )

    with pytest.raises(SimulationRunError, match="conflicting duplicate transition_id"):
        book.transition_run(
            SimulationRunTransitionRequest(
                transition_id="transition-001",
                run_id="sim-run-001",
                status="failed",
                occurred_at="2026-07-08T00:01:30Z",
                reason="operator_stopped",
            ),
        )

    assert len(journal.read_all()) == 2


def test_invalid_transition_fails_without_journaling(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)
    book.create_run(_create_request())
    book.transition_run(
        SimulationRunTransitionRequest(
            transition_id="transition-001",
            run_id="sim-run-001",
            status="completed",
            occurred_at="2026-07-08T00:01:00Z",
            reason="no_strategy_execution_in_slice_024",
        ),
    )

    with pytest.raises(SimulationRunError, match="terminal"):
        book.transition_run(
            SimulationRunTransitionRequest(
                transition_id="transition-002",
                run_id="sim-run-001",
                status="running",
                occurred_at="2026-07-08T00:02:00Z",
                reason="cannot_restart_terminal_run",
            ),
        )

    assert len(journal.read_all()) == 2


def test_simulation_run_model_rejects_unsafe_replay_references_and_invalid_times(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)

    unsafe_references = [
        "https://example.test/replay.jsonl",
        "ibkr://paper/replay.jsonl",
        "fixtures/replay/with token.jsonl",
        " fixtures/replay/aapl.jsonl",
    ]
    for replay_reference in unsafe_references:
        with pytest.raises(SimulationRunError):
            book.create_run(
                SimulationRunCreateRequest(
                    run_id=f"sim-run-{len(journal.read_all()) + 1:03d}",
                    requested_at="2026-07-08T00:00:00Z",
                    replay_input_reference=replay_reference,
                ),
            )

    with pytest.raises(SimulationRunError, match="occurred_at must not be before"):
        book.create_run(_create_request())
        book.transition_run(
            SimulationRunTransitionRequest(
                transition_id="transition-001",
                run_id="sim-run-001",
                status="running",
                occurred_at="2026-07-07T23:59:59Z",
                reason="time_travel",
            ),
        )

    assert len(journal.read_all()) == 1


def test_simulation_run_payloads_exclude_action_broker_network_and_secret_fields(
    tmp_path: Path,
) -> None:
    journal = JsonlEventJournal(tmp_path / "journal.jsonl")
    book = SimulationRunBook(journal)
    run = book.create_run(_create_request())
    book.transition_run(
        SimulationRunTransitionRequest(
            transition_id="transition-001",
            run_id=run.run_id,
            status="running",
            occurred_at="2026-07-08T00:01:00Z",
            reason="replay_loaded",
        ),
    )

    keys = _all_payload_keys(run.to_json_dict())
    for record in journal.read_all():
        keys.update(_all_payload_keys(record.to_json_dict()))

    assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(keys)


def test_simulation_runs_module_does_not_define_transport_or_http_behavior() -> None:
    import trading_oms_backend.simulation_runs as simulation_runs

    source = inspect.getsource(simulation_runs).lower()
    forbidden_source_tokens = [
        "@app.post",
        "@app.put",
        "@app.patch",
        "@app.delete",
        "import socket",
        "from socket",
        "httpx",
        "requests",
        "ibapi",
        "ib_insync",
        "open_connection",
        "create_connection",
        "place_order",
        "submit_order",
        "transmit_order",
    ]
    for token in forbidden_source_tokens:
        assert token not in source


def _create_request() -> SimulationRunCreateRequest:
    return SimulationRunCreateRequest(
        run_id="sim-run-001",
        requested_at="2026-07-08T00:00:00Z",
        replay_input_reference="fixtures/replay/aapl-session.jsonl",
    )


def _all_payload_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested_value in value.values():
            keys.update(_all_payload_keys(nested_value))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_all_payload_keys(item))
        return keys
    return set()
