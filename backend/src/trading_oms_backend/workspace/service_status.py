"""Allowlisted farm identities; unknown messages require dedicated incident review."""

FARMS = frozenset(
    {
        "usfarm",
        "usfarm.nj",
        "cashfarm",
        "eufarm",
        "jfarm",
        "hfarm",
        "afarm",
        "usfuture",
        "usopt",
        "ushmds",
        "euhmds",
        "hkhmds",
        "secdefil",
    }
)
PREFIXES = {
    2103: "market data farm connection is broken",
    2104: "market data farm connection is ok",
    2105: "hmds data farm connection is broken",
    2106: "hmds data farm connection is ok",
    2157: "sec-def data farm connection is broken",
    2158: "sec-def data farm connection is ok",
}


def service_diagnostic(code, message):
    prefix, separator, farm = str(message)[:512].lower().partition(":")
    if code not in PREFIXES or prefix.strip() != PREFIXES[code] or not separator:
        return None
    farm = farm.strip()
    if farm not in FARMS:
        return None
    return {"source": "ibkr_service", "farm": farm, "code": code}


def known_service(diagnostic, code):
    return bool(
        isinstance(diagnostic, dict)
        and diagnostic.get("source") == "ibkr_service"
        and diagnostic.get("code") == code
        and diagnostic.get("farm") in FARMS
    )
