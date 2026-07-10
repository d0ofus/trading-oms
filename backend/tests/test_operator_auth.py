from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from trading_oms_backend.config import Settings
from trading_oms_backend.event_journal import JsonlEventJournal
from trading_oms_backend.operator_auth import (
    ADMINISTER_SYSTEM_PERMISSION,
    APPROVE_SIMULATION_PERMISSION,
    AUTHZ_DECISION_EVENT_TYPE,
    VIEW_OPERATIONS_PERMISSION,
    OperatorAuthError,
    authorize_operator,
    local_development_operator,
    operator_identity_from_headers,
)

ROOT = Path(__file__).resolve().parents[2]


def test_default_local_operator_has_view_and_admin_permissions_without_approval() -> None:
    identity = local_development_operator()

    assert identity.to_json_dict() == {
        "schema_version": 1,
        "operator_id": "human-operator-001",
        "auth_state": "local_development",
        "auth_method": "local_header",
        "roles": ["admin"],
        "permissions": [
            "view_operations",
            "administer_system",
        ],
        "can_view_operations": True,
        "can_approve_simulation": False,
        "can_administer_system": True,
        "approval_role_required": "approver",
        "role_separation": "admin_approver_separated",
    }


def test_approver_role_has_approval_permission_without_admin_permission() -> None:
    identity = operator_identity_from_headers(
        {
            "x-operator-id": "approver-operator-001",
            "x-operator-roles": "approver",
        },
        settings=Settings(app_env="development"),
    )

    assert identity.operator_id == "approver-operator-001"
    assert identity.roles == ("approver",)
    assert identity.permissions == (
        VIEW_OPERATIONS_PERMISSION,
        APPROVE_SIMULATION_PERMISSION,
    )
    assert identity.can_view_operations is True
    assert identity.can_approve_simulation is True
    assert identity.can_administer_system is False


def test_operator_identity_from_headers_derives_viewer_permissions() -> None:
    identity = operator_identity_from_headers(
        {
            "x-operator-id": "viewer-operator-001",
            "x-operator-roles": "viewer",
        },
        settings=Settings(app_env="development"),
    )

    assert identity.operator_id == "viewer-operator-001"
    assert identity.roles == ("viewer",)
    assert identity.permissions == (VIEW_OPERATIONS_PERMISSION,)
    assert identity.can_view_operations is True
    assert identity.can_approve_simulation is False
    assert identity.can_administer_system is False


def test_operator_identity_rejects_unknown_roles_secret_shapes_and_production_local_auth() -> None:
    with pytest.raises(OperatorAuthError, match="unknown operator role"):
        operator_identity_from_headers(
            {"x-operator-roles": "superuser"},
            settings=Settings(app_env="development"),
        )

    with pytest.raises(OperatorAuthError, match="separated"):
        operator_identity_from_headers(
            {"x-operator-roles": "admin,approver"},
            settings=Settings(app_env="development"),
        )

    with pytest.raises(OperatorAuthError, match="operator_id"):
        operator_identity_from_headers(
            {"x-operator-id": "secret-operator"},
            settings=Settings(app_env="development"),
        )

    with pytest.raises(OperatorAuthError, match="production"):
        operator_identity_from_headers(
            {"x-operator-id": "viewer-operator-001"},
            settings=Settings(app_env="production", app_mode="simulation"),
        )


def test_authorize_operator_records_allowed_and_denied_decisions() -> None:
    journal = JsonlEventJournal(_journal_path())
    viewer = operator_identity_from_headers(
        {
            "x-operator-id": "viewer-operator-001",
            "x-operator-roles": "viewer",
        },
        settings=Settings(app_env="development"),
    )

    allowed = authorize_operator(
        viewer,
        permission=VIEW_OPERATIONS_PERMISSION,
        resource="operations_read_model",
        action="view",
        journal=journal,
        decision_id="authz-allowed-001",
        evaluated_at="2026-07-09T00:00:00Z",
    )
    denied = authorize_operator(
        viewer,
        permission=APPROVE_SIMULATION_PERMISSION,
        resource="approval_ticket",
        action="approve",
        journal=journal,
        decision_id="authz-denied-001",
        evaluated_at="2026-07-09T00:00:01Z",
    )

    assert allowed.result == "allowed"
    assert allowed.reason == "permission_present"
    assert denied.result == "denied"
    assert denied.reason == "missing_permission"

    records = journal.read_all()
    assert [record.event_type for record in records] == [
        AUTHZ_DECISION_EVENT_TYPE,
        AUTHZ_DECISION_EVENT_TYPE,
    ]
    assert records[0].payload["result"] == "allowed"
    assert records[1].payload["result"] == "denied"
    assert records[1].payload["permission"] == APPROVE_SIMULATION_PERMISSION
    assert records[1].payload["operator_roles"] == ["viewer"]
    assert records[1].payload["required_role"] == "approver"
    assert records[1].payload["role_separation"] == "admin_approver_separated"


def test_auth_payloads_exclude_broker_live_network_and_secret_affordances() -> None:
    identity = local_development_operator()
    decision = authorize_operator(
        identity,
        permission=ADMINISTER_SYSTEM_PERMISSION,
        resource="workflow_definition",
        action="update",
        journal=JsonlEventJournal(_journal_path()),
        decision_id="authz-safety-001",
        evaluated_at="2026-07-09T00:00:00Z",
    )

    forbidden_keys = {
        "account",
        "account_id",
        "api_key",
        "broker_host",
        "broker_port",
        "certificate",
        "credential",
        "host",
        "password",
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
    assert forbidden_keys.isdisjoint(
        _all_payload_keys(
            {
                "identity": identity.to_json_dict(),
                "decision": decision.to_json_dict(),
            },
        ),
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


def _journal_path() -> Path:
    path = ROOT / ".tmp" / f"operator-auth-{uuid4()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
