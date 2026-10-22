"""Conservative round-trip funding estimates; not commission quotations.

References reviewed 2026-09-23:
https://investors.interactivebrokers.com/en/pricing/commissions-stocks.php
https://investors.interactivebrokers.com/en/index.php?f=1315
No volume discounts, rebates, stamp exemptions or negotiated pricing assumed.
"""

from decimal import ROUND_CEILING, Decimal

from .graph import number

AUTO_REFERENCE = "Automatic stock policy v2"


def fee_reserve(currency, quantity, notional):
    q, value = number(quantity), number(notional)
    if currency == "HKD":
        fixed = max(Decimal(18), value * Decimal("0.0008"))
        tiered = max(Decimal(18), value * Decimal("0.0005"))
        external = sum(
            (value * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
            for rate in ("0.0000565", "0.000042", "0.000027", "0.0000015")
        )
        stamp = (value * Decimal("0.001")).to_integral_value(rounding=ROUND_CEILING)
        result = 2 * (max(fixed, tiered + external) + stamp)
    elif currency == "USD":
        fixed = max(Decimal(1), q * Decimal("0.005"))
        tiered = max(Decimal("0.35"), q * Decimal("0.0035"))
        # Reserve above published exchange/clearing and transaction charges.
        # Do not apply the commission cap or assume any rebates.
        external = q * Decimal("0.01") + value * Decimal("0.0001")
        result = 2 * max(fixed, tiered + external)
    else:
        raise ValueError("Automatic fee-policy coverage is unavailable for this currency.")
    return result.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def branch_fees(contract, quantity, prices):
    rules = contract["stock_rules"]
    if rules["reference"] != AUTO_REFERENCE:
        return number(rules["fee_reserve"]) * len(prices)
    return sum(
        (
            fee_reserve(contract["currency"], quantity, quantity * p * number(rules["price_scale"]))
            for p in prices
        ),
        Decimal(0),
    )
