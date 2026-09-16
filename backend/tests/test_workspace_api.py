from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from trading_oms_backend.workspace.api import create_app
from trading_oms_backend.workspace.graph import templates

PAIRING = "synthetic-local-pairing-for-tests-only"
ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, PAIRING, start_engine=False)
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        assert client.post("/api/auth/pair", json={"token": PAIRING}).status_code == 200
        yield client


def test_local_auth_rejects_external_origin_dns_rebinding_and_reused_pairing(client):
    assert client.get("/api/paper/session").status_code == 200
    assert client.get("/api/paper/session", headers={"Host": "attacker.example"}).status_code == 403
    assert (
        client.post(
            "/api/operations/emergency",
            json={"active": True},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert client.post("/api/auth/pair", json={"token": PAIRING}).status_code == 401
    client.cookies.clear()
    assert client.get("/api/strategies").status_code == 401


def test_draft_publish_and_conflicting_edits_preserve_immutable_versions(client):
    body = {"name": "Test crossover", "document": templates()[1]["document"], "revision": 0}
    draft = client.post("/api/strategies", json=body).json()
    published = client.post(f"/api/strategies/{draft['id']}/publish", json={"revision": 1})
    assert published.status_code == 200
    assert published.json()["explanation"]
    assert (
        client.put(f"/api/strategies/{draft['id']}", json={**body, "revision": 1}).status_code
        == 409
    )
    assert client.get(f"/api/strategies/{draft['id']}/versions").json()[0]["name"] == body["name"]


@pytest.mark.parametrize("mutation", ["settings", "node", "params", "edge"])
def test_malformed_graphs_have_structured_validation_errors(client, mutation):
    graph = deepcopy(templates()[0]["document"])
    if mutation == "settings":
        graph["settings"] = []
    elif mutation == "node":
        graph["nodes"][0] = 42
    elif mutation == "params":
        graph["nodes"][0]["params"] = []
    else:
        graph["edges"][0]["source"] = []
    response = client.post("/api/strategies/validate", json={"document": graph})
    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "invalid_strategy"


def test_emergency_clear_requires_review_and_never_arms_a_run(client):
    assert client.post("/api/operations/emergency", json={"active": True}).status_code == 200
    assert client.get("/api/paper/session").json()["emergency"]
    assert client.post("/api/operations/emergency", json={"active": False}).status_code == 422
    assert (
        client.post(
            "/api/operations/emergency", json={"active": False, "reviewed": True}
        ).status_code
        == 200
    )
    assert client.get("/api/paper/session").json()["entry_permission"] is False


def test_validation_never_echoes_secret_input(client):
    response = client.post(
        "/api/notifications/configure",
        json={"telegram_token": 999, "telegram_chat": "fixture", "healthchecks_url": "fixture"},
    )
    assert response.status_code == 422
    assert "999" not in response.text


def test_retried_mutation_returns_original_result_and_rejects_different_payload(client):
    body = {"name": "One draft", "document": templates()[1]["document"], "revision": 0}
    headers = {"X-Idempotency-Key": "a" * 32}
    first = client.post("/api/strategies", json=body, headers=headers)
    repeated = client.post("/api/strategies", json=body, headers=headers)
    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json()
    assert len(client.get("/api/strategies").json()) == 1
    assert (
        client.post(
            "/api/strategies", json={**body, "name": "Different"}, headers=headers
        ).status_code
        == 409
    )
