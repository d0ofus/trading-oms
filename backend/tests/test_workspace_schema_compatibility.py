import copy

import pytest

from trading_oms_backend.workspace.graph import GraphError, compile_graph, crypto_copy, templates


def stock_document():
    document = copy.deepcopy(templates()[0]["document"])
    document["schema_version"] = 4
    document["settings"].update(trading_hours="regular", stop_limit_offset="0.10")
    return document


def test_legacy_stock_and_crypto_publication_hashes_are_preserved():
    legacy = templates()[0]["document"]
    assert compile_graph(legacy).digest == (
        "6d3b57ea51d653e938392d460678ef904e2e1ee271110c65bf4fec4efc6659dc"
    )
    crypto = compile_graph(crypto_copy(legacy))
    stock = compile_graph(stock_document())
    assert crypto.digest == "524cc00f67202407e485b242815e337b86c5f7a0021b9deb6e4efa3176144ca8"
    assert stock.digest == "f8ea49ad3af117896543dd2c8b716d8085d9b4b7c9ae2707808dd749196ef488"
    assert crypto.document["settings"]["instrument_profile"] == "paxos_crypto"
    assert "instrument_profile" not in stock.document["settings"]
    assert compile_graph(stock.document).digest == stock.digest
    assert compile_graph(crypto.document).digest == crypto.digest


@pytest.mark.parametrize(
    "key,value", [("instrument_profile", "paxos_crypto"), ("quantity", "0.01")]
)
def test_schema_four_mixed_stock_crypto_documents_are_rejected(key, value):
    document = stock_document()
    document["settings"][key] = value
    with pytest.raises(GraphError, match="stock and crypto"):
        compile_graph(document)


def test_unmarked_saved_schema_four_draft_retains_crypto_defaults():
    document = templates()[0]["document"]
    document["schema_version"] = 4
    document["settings"].pop("shares")
    document["settings"]["symbol"] = "BTC"
    assert compile_graph(document).document["settings"]["instrument_profile"] == "paxos_crypto"
