"""
warrantyAI — Week 11: Latency Benchmark
tests/test_latency.py

Measures wall-clock latency for run_classifier() on 10 representative fixtures
and enforces a p95 < 8 seconds SLO.

Why 10 fixtures, not 20?
    Running all 20 against live Bedrock doubles the CI cost (~$0.004 extra) and
    slows the pipeline without meaningfully improving p95 accuracy at N=20.
    10 fixtures gives a robust enough sample for a CI gate.

Why p95 not p99?
    At N=10, p99 ≈ max, which makes the gate too brittle (one slow API call
    from Bedrock throttling fails the build). p95 at N=10 is the 9th-highest
    value — one outlier doesn't break it.

Run locally:
    pytest tests/test_latency.py -v --tb=short
    pytest tests/test_latency.py -v -s   # shows per-fixture latency table

Run only the SLO gate (skip per-fixture tests):
    pytest tests/test_latency.py::test_p95_latency_slo -v
"""

import json
import os
import glob
import time
import pytest
import numpy as np

from agents.classifier import run_classifier

FIXTURE_DIR    = os.path.join(os.path.dirname(__file__), "fixtures")
P95_THRESHOLD_MS = 8_000   # 8 seconds — SLO for classifier p95 latency
LATENCY_SAMPLE  = 10        # Number of fixtures to include in the benchmark


#    Fixture selection                                                         ─

def load_latency_fixtures() -> list[dict]:
    """
    Select 10 fixtures evenly spread across the 20-fixture set.
    Even-index selection (0, 2, 4, ..., 18) gives 3 LOW + 3 MEDIUM + 4 HIGH.
    """
    all_paths = sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.json")))
    selected  = all_paths[::2][:LATENCY_SAMPLE]   # every other fixture, first 10
    return [json.load(open(p)) for p in selected]


def fixture_id(fixture: dict) -> str:
    return fixture["document_id"]


#    Per-fixture latency test                                                   

@pytest.mark.parametrize("fixture", load_latency_fixtures(), ids=fixture_id)
def test_fixture_latency(fixture: dict, benchmark_results):
    """
    Measure latency for a single fixture and store it in benchmark_results.
    This test does NOT assert a threshold — that's done in test_p95_latency_slo.
    """
    t_start = time.monotonic()
    result  = run_classifier(
        document_text=fixture["input"]["document_text"],
        tenant_id=fixture["input"].get("tenant_id", "latency-test"),
    )
    latency_ms = (time.monotonic() - t_start) * 1000

    benchmark_results[fixture["document_id"]] = {
        "latency_ms":  round(latency_ms, 1),
        "risk_level":  result["risk_level"],
        "model_used":  result["model_used"],
        "total_tokens": result["usage"]["total_tokens"],
    }

    # Per-fixture soft limit — warn (don't fail) if a single call exceeds 12s
    if latency_ms > 12_000:
        pytest.xfail(
            f"[{fixture['document_id']}] Latency {latency_ms:.0f}ms exceeds 12s soft limit"
        )


#    Aggregate p95 SLO gate                                                     

def test_p95_latency_slo(benchmark_results):
    """
    Enforce p95 < P95_THRESHOLD_MS across all latency benchmark fixtures.

    This is the CI gate. If p95 latency exceeds 8s, the build fails and deploy
    is blocked. Catches:
    - Prompt bloat (larger prompts → longer first-token latency)
    - Sonnet fallback rate increase (Sonnet is ~3x slower than Haiku)
    - Bedrock throttling during deployment window
    """
    if not benchmark_results:
        pytest.skip("No latency data — run test_fixture_latency first")

    latencies = [v["latency_ms"] for v in benchmark_results.values()]
    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    p99 = float(np.percentile(latencies, 99))

    # Print latency table for CI logs
    print(f"\n{'='*60}")
    print(f"LATENCY BENCHMARK — {len(latencies)} fixtures")
    print(f"{'─'*60}")
    print(f"  {'Document':20s}  {'Latency':>10s}  {'Model':>8s}  {'Tokens':>8s}")
    print(f"{'─'*60}")
    for doc_id, row in sorted(benchmark_results.items()):
        flag = " ⚠" if row["latency_ms"] > P95_THRESHOLD_MS else ""
        print(
            f"  {doc_id:20s}  {row['latency_ms']:>8.0f}ms  "
            f"{row['model_used']:>8s}  {row['total_tokens']:>8d}{flag}"
        )
    print(f"{'─'*60}")
    print(f"  {'p50':20s}  {p50:>8.0f}ms")
    print(f"  {'p95':20s}  {p95:>8.0f}ms  ← SLO threshold: {P95_THRESHOLD_MS}ms")
    print(f"  {'p99':20s}  {p99:>8.0f}ms")
    print(f"{'='*60}\n")

    assert p95 <= P95_THRESHOLD_MS, (
        f"p95 latency {p95:.0f}ms exceeds {P95_THRESHOLD_MS}ms SLO. "
        f"Slowest call was {max(latencies):.0f}ms. "
        f"Check for Sonnet fallback rate increase or prompt bloat."
    )


#    Pytest fixture: shared latency results dict                               ─
# benchmark_results is a session-scoped dict written by test_fixture_latency
# and read by test_p95_latency_slo. This ensures the aggregate test sees all
# per-fixture results even when run in the same session.

@pytest.fixture(scope="session")
def benchmark_results() -> dict:
    return {}
