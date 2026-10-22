import pytest

from trading_oms_backend.workspace.library import StrategyLibrary
from trading_oms_backend.workspace.stock_strategies import stock_templates
from trading_oms_backend.workspace.store import Conflict, Store


def fixture(tmp_path):
    store = Store(tmp_path)
    draft = store.save_draft(None, "Unused", stock_templates()[-1]["document"], 0)
    return store, StrategyLibrary(store), draft


def test_delete_unused_tombstone_idempotency_and_no_resurrection(tmp_path):
    store, library, d = fixture(tmp_path)
    store.put(
        "http_mutation",
        "creation-cache",
        {"hash": "synthetic", "state": "completed", "status": 200, "response": d},
    )
    p = library.preview([d["id"]])
    store.put(
        "http_mutation",
        "preview-cache",
        {"hash": "synthetic2", "state": "completed", "status": 200, "response": p},
    )
    assert p["items"][0]["action"] == "delete"
    r = library.confirm(p["preview_id"], "mutation", "operator")
    assert library.confirm(p["preview_id"], "mutation", "operator") == r
    assert not store.get("draft", d["id"])
    assert "document" not in store.get("http_mutation", "creation-cache")["response"]
    with pytest.raises(Conflict):
        store.save_draft(d["id"], "Resurrect", d["document"], 0)
    assert store.get("strategy_lifecycle", d["id"])["state"] == "deleted"


def test_archive_preserves_versions_and_runs_and_can_restore(tmp_path):
    store, library, d = fixture(tmp_path)
    v = store.publish(d["id"], d["revision"])
    run = {"id": "run", "strategy_id": d["id"], "armed": True, "position": "1"}
    store.put("run", "run", run)
    p = library.preview([d["id"]])
    assert p["items"][0]["action"] == "archive"
    assert p["items"][0]["runs"][0]["armed"]
    library.confirm(p["preview_id"], "mutation", "operator")
    assert not library.listing()
    assert len(library.listing(archived=True)) == 1
    assert store.version(d["id"], 1) == v
    assert store.get("run", "run") == run
    with pytest.raises(Conflict):
        store.publish(d["id"], 2)
    with pytest.raises(Conflict):
        store.save_draft(d["id"], "changed", d["document"], 2)
    library.restore(d["id"], "operator")
    assert len(library.listing()) == 1


def test_concurrent_publication_and_reference_change_invalidate_batch(tmp_path):
    store, library, d = fixture(tmp_path)
    other = store.save_draft(None, "Other", d["document"], 0)
    p = library.preview([d["id"], other["id"]])
    store.put("test_result", "test", {"strategy_id": d["id"]})
    with pytest.raises(Conflict):
        library.confirm(p["preview_id"], "mutation", "operator")
    assert store.get("draft", other["id"])
    assert library.preview([d["id"]])["items"][0]["action"] == "archive"
    p = library.preview([other["id"]])
    store.publish(other["id"], other["revision"])
    with pytest.raises(Conflict):
        library.confirm(p["preview_id"], "mutation2", "operator")
