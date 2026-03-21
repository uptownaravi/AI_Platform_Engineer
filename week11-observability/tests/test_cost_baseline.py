"""
warrantyAI — Week 11: Token Cost Baseline
tests/test_cost_baseline.py

Detects prompt bloat by comparing actual token usage against a locked baseline.

The problem this solves:
    A prompt edit that "looks harmless" can silently double token consumption.
    At 10 CI runs/week × 20 fixtures × 2× token spike = 2× weekly Bedrock cost.
    This test catches it before the change ships to production.

Fail condition:
    avg tokens/doc > baseline_avg * (1 + ALERT_THRESHOLD_PCT / 100)

What it does NOT catch:
    - Per-fixture outliers that don't move the average (add per-fixture check if needed)
    - Cost changes from Bedrock pricing changes (that's a billing alert, not a test)

Run locally:
    pytest tests/test_cost_baseline.py -v --tb=short
    pytest tests/test_cost_baseline.py -v -s   # shows per-fixture token table

Update the baseline after an intentional prompt change:
    make update-baseline
"""

import json
import os
import glob
import pytest

from agents.classifier import run_classifier

FIXTURE_DIR    = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE_FILE  = os.path.join(os.path.dirname(__file__), "baselines", "token_baseline.json")
ALERT_PCT      = 20   # Fail if avg tokens exceeds baseline by more than 20%


#    Helpers                                                                    

def load_fixtures() -> list[dict]:
    paths = sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.json")))
    return [json.load(open(p)) for p in paths]


def load_baseline() -> dict:
    with open(BASELINE_FILE) as f:
        return json.load(f)


def fixture_id(fixture: dict) -> str:
    return fixture["document_id"]


#    Per-fixture token test                                                     

@pytest.mark.parametrize("fixture", load_fixtures(), ids=fixture_id)
def test_fixture_token_count(fixture: dict, token_results):
    """
    Run classifier on each fixture and record actual token usage.
    Does NOT assert a threshold per-fixture — that's done in test_avg_token_cost.
    """
    result = run_classifier(
        document_text=fixture["input"]["document_text"],
        tenant_id=fixture["input"].get("tenant_id", "cost-test"),
    )
    token_results[fixture["document_id"]] = {
        "total_tokens":  result["usage"]["total_tokens"],
        "input_tokens":  result["usage"]["input_tokens"],
        "output_tokens": result["usage"]["output_tokens"],
        "model_used":    result["model_used"],
    }


#    Aggregate cost gate                                                        

def test_avg_token_cost(token_results):
    """
    Fail if average token usage per document exceeds baseline × 1.20.

    This is the deploy gate for prompt bloat. It runs after all
    test_fixture_token_count parametrised tests collect their data.
    """
    if not token_results:
        pytest.skip("No token data — run test_fixture_token_count first")

    baseline   = load_baseline()
    baseline_avg   = baseline["avg_tokens_per_doc"]
    threshold  = baseline_avg * (1 + ALERT_PCT / 100)
    alert_threshold = baseline["alert_threshold"]

    actual_totals = [v["total_tokens"] for v in token_results.values()]
    actual_avg    = sum(actual_totals) / len(actual_totals)

    # Print token usage table for CI logs
    print(f"\n{'='*65}")
    print(f"TOKEN COST BASELINE — {len(actual_totals)} fixtures")
    print(f"{' '*65}")
    print(f"  {'Document':20s}  {'Actual':>8s}  {'Baseline':>8s}  {'Delta':>8s}  {'Model':>8s}")
    print(f"{' '*65}")
    for doc_id, row in sorted(token_results.items()):
        per_fixture_baseline = baseline["per_fixture"].get(doc_id, baseline_avg)
        delta = row["total_tokens"] - per_fixture_baseline
        flag  = " ⚠" if delta > per_fixture_baseline * (ALERT_PCT / 100) else ""
        print(
            f"  {doc_id:20s}  {row['total_tokens']:>8d}  {per_fixture_baseline:>8d}  "
            f"{delta:>+8d}  {row['model_used']:>8s}{flag}"
        )
    print(f"{' '*65}")
    print(f"  {'Baseline avg':20s}  {baseline_avg:>8.0f}")
    print(f"  {'Actual avg':20s}  {actual_avg:>8.1f}  ({'+'if actual_avg >= baseline_avg else ''}{actual_avg - baseline_avg:+.1f})")
    print(f"  {'Alert threshold':20s}  {threshold:>8.0f}  (baseline × {1 + ALERT_PCT/100:.2f})")
    status = "PASS" if actual_avg <= threshold else "FAIL — PROMPT BLOAT DETECTED"
    print(f"  {'Status':20s}  {status}")
    print(f"{'='*65}\n")

    assert actual_avg <= threshold, (
        f"Avg token usage {actual_avg:.1f} tokens/doc exceeds baseline "
        f"{baseline_avg} × {1 + ALERT_PCT/100:.2f} = {threshold:.0f} tokens. "
        f"A prompt change or model update has increased token consumption by "
        f"{((actual_avg / baseline_avg) - 1) * 100:.0f}%. "
        f"Review the prompt diff and update the baseline if the change was intentional: "
        f"make update-baseline"
    )


#    Pytest fixture: shared token results dict                                  

@pytest.fixture(scope="session")
def token_results() -> dict:
    return {}
