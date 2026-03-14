"""
warrantyAI — Week 10: Prompt Regression Test Suite

Runs the Classifier agent against 20 golden fixtures.
Fails the CI build if:
  - Any individual fixture returns a wrong risk_level
  - Aggregate accuracy drops below MIN_ACCURACY (90%)

Run locally:
    pytest tests/test_regression.py -v

Run with summary report:
    pytest tests/test_regression.py -v --tb=short 2>&1 | tee regression_report.txt
"""

import json
import os
import glob
import pytest
from agents.classifier import run_classifier

FIXTURE_DIR  = os.path.join(os.path.dirname(__file__), "fixtures")
MIN_ACCURACY = 0.90   # Deploy gate: fail if accuracy drops below 90%


# ── Fixture loading ───────────────────────────────────────────────────────────

def load_fixtures() -> list[dict]:
    """Load all *.json files from tests/fixtures/ sorted by document_id."""
    paths    = sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.json")))
    fixtures = []
    for p in paths:
        with open(p) as f:
            fixtures.append(json.load(f))
    return fixtures


def fixture_id(fixture: dict) -> str:
    """pytest id: fixture_001, fixture_002, …"""
    return fixture["document_id"]


# ── Per-fixture tests ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("fixture", load_fixtures(), ids=fixture_id)
def test_classifier_risk_level(fixture: dict):
    """
    Each golden fixture must return the expected risk_level.
    This test runs once per fixture file.
    """
    result = run_classifier(
        document_text=fixture["input"]["document_text"],
        tenant_id=fixture["input"].get("tenant_id", "test-tenant"),
    )

    expected    = fixture["expected"]
    expected_rl = expected["risk_level"].lower()
    got_rl      = result["risk_level"].lower()

    assert got_rl == expected_rl, (
        f"[{fixture['document_id']}] "
        f"Expected risk_level={expected_rl!r}, got {got_rl!r}. "
        f"Reasoning: {result.get('reasoning', 'N/A')}"
    )


@pytest.mark.parametrize("fixture", load_fixtures(), ids=fixture_id)
def test_classifier_confidence_floor(fixture: dict):
    """
    Where confidence_min is specified, the model must meet it.
    Catches regressions where the agent is correct but unusually uncertain.
    """
    expected = fixture["expected"]
    if "confidence_min" not in expected:
        pytest.skip("No confidence_min specified for this fixture")

    result = run_classifier(
        document_text=fixture["input"]["document_text"],
        tenant_id=fixture["input"].get("tenant_id", "test-tenant"),
    )

    assert result["confidence"] >= expected["confidence_min"], (
        f"[{fixture['document_id']}] "
        f"Confidence {result['confidence']:.2f} below minimum "
        f"{expected['confidence_min']:.2f}"
    )


# ── Aggregate accuracy gate ───────────────────────────────────────────────────

def test_overall_accuracy():
    """
    Fail the entire suite if aggregate accuracy < MIN_ACCURACY.

    This is the deploy gate: even if individual fixtures pass on edge cases,
    a systemic accuracy drop — caused by a prompt edit, model update, or parser
    change — will block the deployment.
    """
    fixtures = load_fixtures()
    passed   = 0
    failures = []

    for fixture in fixtures:
        result = run_classifier(
            document_text=fixture["input"]["document_text"],
            tenant_id=fixture["input"].get("tenant_id", "test-tenant"),
        )
        expected_rl = fixture["expected"]["risk_level"].lower()
        got_rl      = result["risk_level"].lower()

        if got_rl == expected_rl:
            passed += 1
        else:
            failures.append({
                "document_id":  fixture["document_id"],
                "expected":     expected_rl,
                "got":          got_rl,
                "reasoning":    result.get("reasoning", ""),
            })

    accuracy = passed / len(fixtures)

    # Print regression diff for CI logs
    if failures:
        print(f"\n{'='*60}")
        print(f"REGRESSION DIFF — {len(failures)} fixture(s) changed classification:")
        print(f"{'─'*60}")
        for f in failures:
            print(f"  {f['document_id']:15s}  {f['expected']:6s} → {f['got']:6s}  | {f['reasoning'][:60]}")
        print(f"{'='*60}\n")

    assert accuracy >= MIN_ACCURACY, (
        f"Accuracy {accuracy:.0%} is below threshold {MIN_ACCURACY:.0%}. "
        f"Passed {passed}/{len(fixtures)} fixtures. "
        f"Deploy blocked — fix the {len(failures)} regression(s) above."
    )
