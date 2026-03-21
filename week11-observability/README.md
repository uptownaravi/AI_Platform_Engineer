# warrantyAI — Week 11: Observability + Canary Deploy

Week 11 answers the question Week 10 left open: you can now detect regressions before deploy — but can you see what's happening in production?

This week adds **LangSmith tracing**, **CloudWatch custom metrics**, a **latency SLO gate** in CI, and **Lambda canary deploys** so you can validate a new version on real traffic before going 100%.

---

## What Changed from Week 10

| Concern | Week 10 | Week 11 |
|---|---|---|
| Production visibility | None — deploy and hope | CloudWatch dashboard: latency, tokens, fallback rate, risk distribution |
| Agent tracing | None | LangSmith: every classifier call traced with inputs, outputs, latency, token counts |
| CI gates | Accuracy ≥ 90% | + p95 latency < 8s + avg tokens within 20% of baseline |
| Deploy strategy | Update $LATEST → Lambda | Publish version → staging alias → manual approval → production alias |
| Rollback | Re-run CI with old code | `make rollback VERSION=3` — instant, no rebuild |

---

## Repository Layout

```
week11-observability/
├── agents/
│   └── classifier.py           ← Week 10 classifier + LangSmith @traceable + CloudWatch metrics
├── observability/
│   ├── langsmith_tracer.py     ← @traceable decorator (no-op when tracing disabled)
│   └── cloudwatch_metrics.py  ← emit_classifier_metrics()
├── tests/
│   ├── test_latency.py         ← p95 < 8s benchmark (10 fixtures)
│   ├── test_cost_baseline.py   ← avg tokens within 20% of baseline (20 fixtures)
│   ├── test_regression.py      ← Week 10 regression suite (20 fixtures, ≥ 90%)
│   ├── fixtures/               ← 20 golden fixtures (copied from Week 10)
│   └── baselines/
│       └── token_baseline.json ← locked token counts per fixture
├── infra/
│   ├── canary.tf               ← Lambda aliases: staging + production
│   ├── cloudwatch_dashboard.tf ← 3 alarms + 4-widget dashboard
│   ├── variables.tf
│   └── outputs.tf
├── scripts/
│   └── promote_canary.py       ← canary / promote / rollback
├── .github/
│   └── workflows/
│       └── deploy.yml          ← 4-job pipeline: regression → latency → staging → production
├── Makefile
└── requirements.txt
```

---

## LangSmith Tracing

Every `run_classifier()` call is traced automatically when three env vars are set:

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-langsmith-key>
export LANGCHAIN_PROJECT=warrantyai-production
```

What each trace captures:

| Field | Value |
|---|---|
| Inputs | `document_text` (truncated to 500 chars — PII protection), `tenant_id` |
| Outputs | `risk_level`, `confidence`, `category`, `model_used`, token totals |
| Metadata | `aws_region`, `function_version`, `git_sha`, `environment` |
| Latency | Wall-clock time (measured by LangSmith automatically) |

When these env vars are absent, `@traceable` is a **no-op** — the decorator returns the original function unchanged. No code changes between traced and un-traced environments.

### Get a LangSmith API key

1. Sign up at [smith.langchain.com](https://smith.langchain.com) (free tier: 5,000 traces/month)
2. Settings → API Keys → Create API Key
3. Add to Lambda env vars or `.env`:
   ```
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=lsv2_pt_...
   LANGCHAIN_PROJECT=warrantyai-production
   ```

---

## CloudWatch Custom Metrics

Emitted via `observability/cloudwatch_metrics.py` after every classifier call.

**Namespace:** `WarrantyAI/Agent`

| Metric | Unit | What it catches |
|---|---|---|
| `ClassifierLatency` | Milliseconds | Slow calls from prompt bloat or Sonnet fallback increase |
| `TokensUsed` | Count | Token cost per document |
| `ModelFallback` | Count (0 or 1) | Rate of Haiku→Sonnet fallbacks |
| `RiskLevelHigh` | Count (0 or 1) | % of high-risk documents (business signal) |
| `RiskLevelMedium` | Count (0 or 1) | % of medium-risk documents |
| `RiskLevelLow` | Count (0 or 1) | % of low-risk documents |

**Dimensions:** `AgentName=classifier`, `TenantId=<tenant_id>`

Metrics are skipped if `EMIT_METRICS != "true"` — CI sets this to `"false"` so benchmark runs don't pollute production metrics.

---

## CI Pipeline (Week 11)

```
Push to main / PR
      │
      ▼
Job 1: Prompt Regression Tests     20 fixtures · ≥ 90% accuracy  (Week 10)
      │
      ▼
Job 2: Latency Benchmark           10 fixtures · p95 < 8s        (Week 11)
      │
      │ (main branch only)
      ▼
Job 3: Build → ECR → Lambda staging
      ├── docker build + push to ECR
      ├── aws lambda update-function-code
      ├── aws lambda publish-version  → new immutable version number
      ├── update staging alias → new version
      └── smoke test staging alias
      │
      │ (requires GitHub Environment approval — "production" environment)
      ▼
Job 4: Promote staging → production
      └── python scripts/promote_canary.py --promote
```

### One-time setup: GitHub Environment

1. GitHub → Settings → Environments → New environment → `production`
2. Add required reviewers (yourself)
3. This gate appears in the Actions UI as a "Review deployments" button before Job 4 runs

---

## Canary Deploy

Before promoting 100% to production, optionally route a fraction of traffic to test the new version on real requests:

```bash
# 1. Check current versions
make status
#   staging    → v4
#   production → v3

# 2. Route 10% of production traffic to v4
make canary
#   Setting canary: 90% → v3  |  10% → v4

# 3. Monitor CloudWatch for 15 minutes
make dashboard

# 4. Promote 100% if healthy
make promote
#   Production alias → v4. Done.

# Or rollback if something looks wrong
make rollback VERSION=3
```

---

## Latency Benchmark

```bash
make test-latency
```

Sample output (passing):
```
============================================================
LATENCY BENCHMARK — 10 fixtures
────────────────────────────────────────────────────────────
  Document              Latency     Model    Tokens
────────────────────────────────────────────────────────────
  fixture_001          1,240ms      haiku       520
  fixture_003          1,380ms      haiku       510
  fixture_005          1,290ms      haiku       530
  fixture_007          1,410ms      haiku       555
  fixture_009          1,350ms      haiku       540
  fixture_011          1,480ms      haiku       565
  fixture_013          1,390ms      haiku       558
  fixture_015          3,820ms     sonnet       840  ← Sonnet fallback
  fixture_017          1,440ms      haiku       545
  fixture_019          1,350ms      haiku       540
────────────────────────────────────────────────────────────
  p50                  1,385ms
  p95                  3,145ms  ← SLO threshold: 8000ms
  p99                  3,820ms
============================================================
10 passed in 18.3s
```

Sample output (SLO breach):
```
FAILED tests/test_latency.py::test_p95_latency_slo
p95 latency 9420ms exceeds 8000ms SLO. Slowest call was 11,240ms.
Check for Sonnet fallback rate increase or prompt bloat.
```

---

## Token Cost Baseline

```bash
# Check current usage against baseline
make test-cost

# Update baseline after an intentional prompt change
make update-baseline
git add tests/baselines/token_baseline.json
git commit -m "chore: update token baseline after prompt change"
```

**Rule:** Never auto-update the baseline in CI. Only update manually after a deliberate change, and commit the updated file with the prompt diff.

---

## CloudWatch Alarms

| Alarm | Threshold | What it catches |
|---|---|---|
| `warrantyai-classifier-latency-high` | p95 > 8,000ms | Prompt bloat, Bedrock throttling, Sonnet fallback spike |
| `warrantyai-token-cost-spike` | avg tokens > 660 | Accidental prompt length increase |
| `warrantyai-model-fallback-rate-high` | fallback rate > 30% | Prompt change degrading Haiku performance |

To enable alarm notifications, pass your SNS topic ARN:
```bash
cd infra && terraform apply -var="alarm_sns_topic_arn=arn:aws:sns:ap-south-1:123456789012:warrantyai-alerts"
```

---

## One-Time Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Deploy CloudWatch dashboard + Lambda aliases (requires existing Lambda)
make deploy-infra

# 3. Publish an initial Lambda version (aliases need at least one version)
aws lambda publish-version --function-name warrantyai-langgraph-pipeline

# 4. Set LangSmith env vars (optional — tracing is off without these)
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=lsv2_pt_...
export LANGCHAIN_PROJECT=warrantyai-production

# 5. Run all tests
make test-all
```

---

## Cost

| CI run | Bedrock calls | Est. cost |
|---|---|---|
| Regression (20 fixtures) | 20 × Haiku | ~$0.002 |
| Latency benchmark (10 fixtures) | 10 × Haiku | ~$0.001 |
| Token cost check (20 fixtures) | 20 × Haiku | ~$0.002 |
| **Total per CI run** | 50 × Haiku | **~$0.005** |

At ~10 PRs/week: **< $0.05/week**.

CloudWatch custom metrics: ~$0.30/month per metric (6 metrics × $0.30 = $1.80/month).

LangSmith: Free tier covers 5,000 traces/month.

---

## Next Week (Week 12)

- Deploy warrantyAI's agent techniques inside apartmentwise.in as a paid AI add-on
- Maintenance Prediction Agent: input 12 months of maintenance records → predict next failure
- Stripe: ₹500/month "AI Insights" add-on
