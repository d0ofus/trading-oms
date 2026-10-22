"""Narrow, versioned recovery for the audited pre-resolution history defect."""

POLICY = "corrected_data_request_v1"
# Audited 2026-09-24: ValueError from history before contract resolution, via
# _loop/maintain/_premarket_maintain. The scheduler now fences and isolates it.
# Fingerprints include code locations; other ValueErrors do not qualify.
CORRECTED = frozenset({"6120a896001cbf3769738e4a"})


def record_faults(item, diagnostic, previous_occurrences):
    prior = item.get("fault_fingerprints")
    if prior is None:
        prior = []
        if previous_occurrences:
            old = (item.get("diagnostic") or {}).get("fingerprint")
            prior = [old] if previous_occurrences == 1 else [None]
    fingerprint = (diagnostic or {}).get("fingerprint")
    item["fault_fingerprints"] = list(dict.fromkeys([*prior, fingerprint]))[:9]


def corrected_episode(item):
    fingerprints = item.get("fault_fingerprints")
    if fingerprints is None:
        # Legacy aggregate records did not prove the diagnostic of every call.
        fingerprints = (
            [(item.get("diagnostic") or {}).get("fingerprint")]
            if (item.get("occurrences") == 1)
            else [None]
        )
    return bool(fingerprints) and set(fingerprints) <= CORRECTED
