import pytest
from fastapi.testclient import TestClient

from trading_oms_backend.workspace.api import create_app
from trading_oms_backend.workspace.store import Conflict

ORIGIN = "http://127.0.0.1:8000"
PAIRING = "synthetic-incident-api-pairing-only"


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, PAIRING, start_engine=False)
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        assert client.post("/api/auth/pair", json={"token": PAIRING}).status_code == 200
        yield client


def test_incident_pages_are_authenticated_bounded_and_details_are_lazy(client):
    book = client.app.state.engine.incidents
    for conid in range(1, 205):
        book.raise_incident(
            "market_data_failure", "Fixture contract failure", "fixture", conid=conid, notify=False
        )
    assert not client.get("/api/incidents").json()["items"]
    first = client.get("/api/incidents?view=diagnostics").json()
    assert len(first["items"]) == 200 and first["next_cursor"]
    assert "diagnostic" not in first["items"][0]
    older = client.get(f"/api/incidents?view=diagnostics&before={first['next_cursor']}").json()
    assert len(older["items"]) == 4
    assert client.get("/api/incidents?limit=201").status_code == 422
    item = first["items"][0]
    assert client.get(f"/api/incidents/{item['id']}").json()["code"] == "market_data_failure"
    assert (
        client.post("/api/operations/incidents/market_data_failure/review", json={}).status_code
        == 409
    )
    client.cookies.clear()
    assert client.get("/api/incidents").status_code == 401


def test_actor_comes_from_authenticated_session_never_cookie_or_request_payload(
    client, monkeypatch
):
    received = []
    monkeypatch.setattr(
        client.app.state.engine,
        "review_incident",
        lambda **kwargs: received.append(kwargs) or {"reviewed": True},
    )
    assert (
        client.post(
            "/api/operations/incidents/fixture/review",
            json={"revision": 1, "rationale": "Inspected recovery evidence"},
        ).status_code
        == 200
    )
    actor = received[0]["actor"]
    assert actor.startswith("operator-")
    assert actor not in client.cookies.values()
    assert PAIRING not in str(received)
    assert (
        client.post(
            "/api/operations/incidents/fixture/review", json={"actor": "forged"}
        ).status_code
        == 422
    )


def test_investigation_closure_never_releases_a_hold(client):
    engine = client.app.state.engine
    episode = engine.incident("engine_fault", "Fixture fault")
    with pytest.raises(Conflict):
        engine.incidents.close_investigation(
            episode["id"], episode["revision"], "fixture", "Reviewed diagnostics"
        )
    with engine.store.transaction() as db:
        ready = engine.incidents.recover_in(db, episode, {"fixture": True})
        released = engine.incidents.release_in(
            db, ready["id"], ready["revision"], "fixture", "Verified recovery"
        )
    response = client.post(
        f"/api/incidents/{released['id']}/investigation/close",
        json={"revision": released["revision"], "rationale": "Recorded test remediation evidence"},
    )
    assert response.status_code == 200
    assert response.json()["investigation"] == "closed"
    assert response.json()["restriction"] == "released"
    assert not client.get("/api/incidents?view=investigations").json()["items"]
    assert len(client.get("/api/incidents?view=history").json()["items"]) == 1


def test_build_status_has_no_operator_identity(client):
    build = client.get("/healthz").json()["build"]
    assert len(build["backend"]) == 16
    assert set(build) == {"backend", "frontend", "started_at"}
