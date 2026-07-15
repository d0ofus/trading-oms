from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXECPLAN = ROOT / "docs" / "execplans" / "candidate-slice-062-ibkr-paper-connector-execplan.md"
SLICES = ROOT / "docs" / "SLICES.md"
SECURITY = ROOT / "docs" / "SECURITY_BASELINE.md"
README = ROOT / "README.md"
PYPROJECT = ROOT / "backend" / "pyproject.toml"
REQUIREMENTS = ROOT / "backend" / "requirements-dev.txt"
BACKEND_SOURCE = ROOT / "backend" / "src" / "trading_oms_backend"


def test_candidate_slice_062_execplan_uses_required_structure_and_source_distinctions() -> None:
    text = EXECPLAN.read_text(encoding="utf-8")
    required_sections = [
        "## 1. Goal",
        "## 2. Non-goals",
        "## 3. Safety constraints",
        "## 4. Current state",
        "## 5. Proposed design",
        "## 6. Data model changes",
        "## 7. API changes",
        "## 8. Test plan",
        "## 9. Verification commands",
        "## 10. Rollback plan",
        "## 11. Implementation steps",
        "## 12. Completion criteria",
        "## 13. Risks and assumptions",
    ]
    for section in required_sections:
        assert section in text

    required_distinctions = [
        "### Repository facts",
        "### Current official IBKR facts",
        "### Design recommendations and unresolved blockers",
        "reviewed on 2026-07-15",
        "Candidate Slice 062 is transport planning only.",
        "Candidate 062 planning does not constitute independent review",
    ]
    for phrase in required_distinctions:
        assert phrase.casefold() in text.casefold()


def test_candidate_slice_062_selects_only_the_current_official_native_python_sdk() -> None:
    text = EXECPLAN.read_text(encoding="utf-8")
    required_sdk_content = [
        "official **IBKR TWS API Latest 10.48** distribution",
        "`EClient`/`EWrapper`/reader architecture",
        "https://interactivebrokers.github.io/",
        "The TWS API is available only through the official MSI or ZIP download.",
        "public `pip`, NuGet, or other repository copies are not hosted, endorsed, supported",
        "`ib_insync` is legacy and no longer updated",
        "`ib_async` is not endorsed",
        "synchronous wrapper is beta",
        "exact official artifact filename, SHA-256 digest",
        "license acceptance and redistribution decision",
    ]
    for phrase in required_sdk_content:
        assert phrase.casefold() in text.casefold()


def test_candidate_slice_062_covers_connector_safety_and_failure_design() -> None:
    text = EXECPLAN.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split()).casefold()
    required_design_content = [
        "### 5.1 Connector boundary and dependency isolation",
        "### 5.2 Default-off, localhost-only transport",
        "The only permitted ports are TWS paper `7497` and IB Gateway paper `4002`.",
        "paper port and `account_mode=paper` are necessary controls but are not proof",
        "### 5.3 Session lifecycle",
        "`unknown_requires_reconciliation`",
        "### 5.4 Paper-mode proof and private values",
        "private-value injection rule permits no generic secret/config/CLI/API surface",
        "non-serializable memory-only context",
        "accepts exactly one accessible account",
        "No prefix or value pattern may select or classify an account.",
        "### 5.5 Contract resolution",
        "`contractDetailsEnd`",
        "### 5.6 Atomic pre-transport gate",
        "current explicit human approval",
        "emergency stop is inactive",
        "### 5.7 Durable idempotency, client ID, and order reference",
        "durable append-only outbox reservation",
        "stable nonzero client ID",
        "### 5.8 Callback, order, fill, reject, and cancel reduction",
        "| Broker status class | Reduction rule |",
        "`Inactive` | Ambiguous without correlated order/error context",
        "`PendingCancel` remains working risk",
        "### 5.9 Disconnect, reconnect, and reconciliation",
        "codes 1100/1101/1102/1300",
        "never automatically replays",
        "### 5.10 Protection, partial fills, and emergency behavior",
        "critical alert",
        "does not auto-flatten, auto-liquidate, global-cancel",
        "### 5.11 Failure matrix",
        "Stale market data or stale contract",
        "Conflicting duplicate",
        "Out-of-order callback",
        "Disconnect during/after dispatch",
        "Partial fill",
        "### 5.12 Bounded future paper-lab acceptance criteria",
        "### 5.13 External design-review checklist",
        "**Architecture reviewer**",
        "**Trading-safety reviewer**",
        "**Security reviewer**",
        "### Explicit Candidate 063 entry criteria",
    ]
    for phrase in required_design_content:
        assert " ".join(phrase.split()).casefold() in normalized_text


def test_candidate_slice_062_keeps_evidence_and_readiness_fail_closed() -> None:
    text = EXECPLAN.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split()).casefold()
    required_posture = [
        "Readiness remains `not_ready`",
        "decision remains `no_go`",
        "external-review evidence remains `missing`",
        "zero controlled-rollout evidence categories are verified",
        "all 14 unresolved mandatory categories remain blocking",
        "does not perform external review",
        "No paper lab occurs in Candidate 062",
        "does not authorize IBKR contact or a paper lab",
        "Stop. Do not begin Candidate 063",
    ]
    for phrase in required_posture:
        assert " ".join(phrase.split()).casefold() in normalized_text

    forbidden_patterns = [
        r"current result:\s*`ready_for_final_review`",
        r"current result:\s*`ready_for_rollout`",
        r"live[_ ]trading[_ ]enabled\s*[:=]\s*true",
        r"live[_ ]trading[_ ]authorized\s*[:=]\s*true",
        r"production rollout (?:is )?approved",
        r"real ibkr paper(?:-account)? connectivity (?:is|has been) demonstrated",
        r"external-review evidence (?:is )?verified",
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
        r"\b[DUF]\d{7,}\b",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, text, flags=re.IGNORECASE) is None


def test_candidate_slice_062_adds_no_sdk_or_connector_runtime_surface() -> None:
    dependencies = (
        PYPROJECT.read_text(encoding="utf-8") + "\n" + REQUIREMENTS.read_text(encoding="utf-8")
    ).casefold()
    for package in ("ibapi", "ib_insync", "ib-async", "ib_async"):
        assert package not in dependencies

    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(BACKEND_SOURCE.rglob("*.py"))
    ).casefold()
    forbidden_source = [
        "from ibapi",
        "import ibapi",
        "from ib_insync",
        "import ib_insync",
        "from ib_async",
        "import ib_async",
        "class officialtwspaperconnector",
        "ibkr_paper_transport_enabled",
    ]
    for token in forbidden_source:
        assert token not in sources


def test_candidate_slice_062_is_documented_as_plan_only_and_ready_for_review() -> None:
    slices_text = SLICES.read_text(encoding="utf-8")
    security_text = SECURITY.read_text(encoding="utf-8")
    readme_text = README.read_text(encoding="utf-8")

    section_match = re.search(
        r"## Candidate Slice 062 - concrete IBKR paper connector ExecPlan.*?(?=\n---\n|\Z)",
        slices_text,
        flags=re.DOTALL,
    )
    assert section_match is not None
    section = section_match.group(0)
    assert "status: `ready_for_human_review`" in section
    assert "branch: `candidate-slice-062-ibkr-paper-connector-execplan`" in section
    assert "planning only" in section.casefold()
    assert "Candidate 063" in section

    required_security = [
        "Candidate Slice 062 is connector planning only.",
        "TWS API Latest 10.48",
        "does not add an SDK, broker connection, authenticated session, or order path",
        "External-review evidence remains missing",
    ]
    for phrase in required_security:
        assert phrase.casefold() in security_text.casefold()

    required_readme = [
        "Candidate Slice 062 concrete connector ExecPlan",
        "planning-only",
        "does not install an SDK or contact IBKR",
    ]
    for phrase in required_readme:
        assert phrase.casefold() in readme_text.casefold()
