"""Read-only FX quotes used exclusively for stock valuation, never FX orders."""

from datetime import UTC, datetime


class BrokerValuation:
    def subscribe_fx(self, currency):
        if currency == "USD" or not self.client or not self.client.isConnected():
            return
        if currency not in {
            "HKD",
            "JPY",
            "CAD",
            "CHF",
            "EUR",
            "GBP",
            "AUD",
            "NZD",
            "SGD",
            "CNH",
            "SEK",
            "NOK",
            "DKK",
            "MXN",
            "ZAR",
            "PLN",
            "HUF",
            "CZK",
            "ILS",
        }:
            return  # Unknown pairs remain unavailable, never guess a conversion rate.
        if any(c["currency"] == currency for c in self._fx_requests.values()):
            return
        from ibapi.contract import Contract

        contract = Contract()
        contract.secType, contract.exchange = "CASH", "IDEALPRO"
        contract.symbol, contract.currency = (
            (currency, "USD") if currency in {"EUR", "GBP", "AUD", "NZD"} else ("USD", currency)
        )
        self._request_id += 1
        request = self._request_id
        self._fx_requests[request] = {
            "currency": currency,
            "base": contract.symbol,
            "quote": contract.currency,
        }
        self.client.reqMktData(request, contract, "", False, False, [])

    def fx_observation(self, request, **fields):
        context = self._fx_requests.get(request)
        if context:
            self.emit(
                "fx_quote",
                base=context["base"],
                quote=context["quote"],
                received_at=datetime.now(UTC).isoformat(),
                **fields,
            )
