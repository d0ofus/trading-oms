import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW_DOC = ROOT / "docs" / "POST_SLICE_059_REVIEW.md"
EXECPLAN_DOC = ROOT / "docs" / "execplans" / "post-slice-059-closeout-review.md"


def test_closeout_review_and_execplan_exist() -> None:
    assert REVIEW_DOC.exists(), f"{REVIEW_DOC.relative_to(ROOT)} is missing"
    assert EXECPLAN_DOC.exists(), f"{EXECPLAN_DOC.relative_to(ROOT)} is missing"


def test_closeout_review_contains_required_traceability_and_evidence_sections() -> None:
    text = REVIEW_DOC.read_text(encoding="utf-8")
    required_phrases = [
        "Evidence-level vocabulary",
        "Product requirements traceability",
        "Roadmap traceability",
        "Runtime inspection",
        "Capability inventory",
        "Explicit IBKR verdict",
        "Controlled paper-production checklist mapping",
        "Missing evidence",
        "Prioritized evidence program",
        "Human approval gates and external dependencies",
        "Recommended follow-up slices",
        "Real IBKR paper-account connectivity has not been demonstrated.",
        "Real IBKR paper-order execution has not been demonstrated.",
        "Local TCP reachability is not an authenticated IBKR paper session.",
        "Injected connector test doubles are not broker evidence.",
        "The in-app browser runtime had no available browser instance.",
        "Missing, unverified, expired, or contradictory evidence remains blocking.",
        "Recommendations only; none of these slices is approved.",
    ]
    for phrase in required_phrases:
        assert phrase.casefold() in text.casefold()


def test_closeout_review_maps_every_controlled_rollout_evidence_category() -> None:
    text = REVIEW_DOC.read_text(encoding="utf-8")
    required_categories = [
        "External review evidence",
        "Paper-trading history evidence",
        "Live-readiness evidence",
        "Secret-management review",
        "Network-exposure review",
        "Authentication and authorization evidence",
        "Emergency-stop evidence",
        "Observability evidence",
        "Audit-retention evidence",
        "Backup and restore evidence",
        "Reconciliation evidence",
        "Rollback evidence",
        "Incident-response evidence",
        "Operator sign-off evidence",
    ]
    for category in required_categories:
        assert category.casefold() in text.casefold()


def test_closeout_review_remains_fail_closed_and_contains_no_fabricated_evidence() -> None:
    text = REVIEW_DOC.read_text(encoding="utf-8")
    forbidden_patterns = [
        r"current result:\s*`ready_for_final_review`",
        r"current result:\s*`ready_for_rollout`",
        r"live[_ ]trading[_ ]enabled\s*[:=]\s*true",
        r"live[_ ]trading[_ ]authorized\s*[:=]\s*true",
        r"production rollout (?:is )?approved",
        r"controlled rollout (?:is )?approved",
        r"real ibkr paper(?:-account)? connectivity (?:is|has been) demonstrated",
        r"real ibkr paper(?:-order)? execution (?:is|has been) demonstrated",
        r"external review (?:is )?complete",
        r"paper-trading history (?:is )?(?:complete|approved)",
        r"public ibkr ports are allowed",
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, text, flags=re.IGNORECASE) is None


def test_closeout_execplan_uses_all_required_sections() -> None:
    text = EXECPLAN_DOC.read_text(encoding="utf-8")
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
