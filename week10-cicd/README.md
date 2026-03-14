# warrantyAI — Week 10: CI/CD + Prompt Regression Tests

Week 10 adds a deploy gate to the warrantyAI pipeline: **prompt regression tests that block deployment if the Classifier agent's accuracy drops below 90%**.

The pipeline is: GitHub Actions → Prompt regression tests (live Bedrock) → Docker build → ECR push → Lambda update.

---

## What Changed from Week 9

| Concern | Week 9 | Week 10 |
|---|---|---|
| Deployment | `make deploy` (Terraform) | GitHub Actions CI/CD |
| Container | Lambda zip package | Docker image via ECR |
| Testing | Unit tests (mocked) | **Regression tests (live Bedrock)** |
| Deploy gate | None | Accuracy ≥ 90% required to merge |
| AWS credentials | Long-lived keys | OIDC — no stored keys |

---

## The Problem This Solves

A LangGraph agent has three moving parts that can silently break production:
- The **prompt** — an edit that "looks harmless" shifts edge-case classification
- The **model** — a version update changes output structure or confidence
- The **output parser** — a refactor introduces a subtle bug

Traditional unit tests with mocked Bedrock responses don't catch any of these. The regression suite catches all three by running **known documents against the live model on every deploy**.

---

## Repository Layout

```
week10-cicd-regression/
├── .github/
│   └── workflows/
│       └── deploy.yml          ← CI/CD pipeline
├── agents/
│   └── classifier.py           ← run_classifier() wrapper for testing
├── tests/
│   ├── conftest.py             ← sys.path setup
│   ├── test_regression.py      ← regression test suite
│   └── fixtures/               ← 20 golden fixtures
│       ├── fixture_001.json    ← LOW: refrigerator, 3-year warranty
│       ├── ...
│       ├── fixture_014.json    ← MEDIUM: water heater, 110 days left
│       ├── fixture_015.json    ← HIGH: TV, 15 days left
│       └── fixture_020.json    ← HIGH: generator, 3-month warranty
├── infra/
│   └── oidc.tf                 ← GitHub Actions OIDC IAM role + ECR
├── Dockerfile                  ← Lambda container image
├── Makefile                    ← Local commands
└── requirements.txt
```

---

## Fixture Design

20 golden fixtures locked in version control. Written manually — never auto-generated. Covers:

| Risk Level | Count | Example cases |
|---|---|---|
| **low** | 7 | New purchase, warranty > 6 months remaining |
| **medium** | 7 | 90–180 days remaining — standard monitoring |
| **high** | 6 | < 90 days remaining, OR total warranty < 6 months |

Each fixture has:
- `document_id` — unique identifier for regression diff output
- `input.document_text` — the raw warranty text fed to the Classifier
- `expected.risk_level` — the correct answer a human has verified
- `expected.confidence_min` — minimum acceptable model confidence (optional)

**Rule for adding fixtures:** Every time a production bug surfaces from a new edge case, add a fixture for it before fixing the agent. The fixture set gets more valuable over time.

---

## Test Runner

```
tests/test_regression.py
├── test_classifier_risk_level()    — per-fixture: correct risk_level?
├── test_classifier_confidence_floor() — per-fixture: confidence ≥ minimum?
└── test_overall_accuracy()         — aggregate: ≥ 90% accuracy or build fails
```

The `test_overall_accuracy()` test is the deploy gate. It runs all 20 fixtures and prints a **regression diff** showing which documents changed classification and in which direction.

---

## Running Locally

```bash
# Install dependencies (requires Python 3.12 + AWS credentials with Bedrock access)
pip install -r requirements.txt

# Run all regression tests
make test

# Run only the accuracy gate (faster)
make regression

# Run in parallel (20 fixtures concurrently)
make test-parallel

# Show fixture distribution
make fixtures
```

Expected output (passing):
```
tests/test_regression.py::test_classifier_risk_level[fixture_001] PASSED
tests/test_regression.py::test_classifier_risk_level[fixture_002] PASSED
...
tests/test_regression.py::test_overall_accuracy PASSED
20 passed in 35.2s
```

Expected output (regression detected):
```
============================================================
REGRESSION DIFF — 2 fixture(s) changed classification:
────────────────────────────────────────────────────────────
  fixture_008       medium → low   | Expiry date not found, defaulted to low
  fixture_015       high   → medium | 15 days treated as medium boundary
============================================================
FAILED tests/test_regression.py::test_overall_accuracy
Accuracy 90% is below threshold 90%. Passed 18/20 fixtures. Deploy blocked.
```

---

## CI/CD Pipeline

### Flow

```
Push to main / open PR
        │
        ▼
Job 1: regression-tests
  ├── Configure AWS credentials (OIDC — no long-lived keys)
  ├── Run: pytest tests/test_regression.py -v
  ├── Upload regression report as artifact
  ├── Post results as PR comment
  └── Pass / Fail
        │
        │ (only on main branch, only if tests pass)
        ▼
Job 2: build-and-deploy
  ├── Build Docker image (ARM64)
  ├── Push to ECR with git SHA tag
  ├── aws lambda update-function-code
  ├── aws lambda wait function-updated
  └── Verify Lambda state = Active
```

### Required GitHub Secrets

| Secret | Value | Where to get it |
|---|---|---|
| `AWS_ROLE_ARN` | OIDC role ARN | `cd infra && terraform output github_actions_role_arn` |
| `ECR_REGISTRY` | `<account>.dkr.ecr.ap-south-1.amazonaws.com` | `cd infra && terraform output ecr_registry` |

### Pull Request behaviour

- Regression tests run on every PR → results posted as a PR comment
- Deploy job is skipped on PRs (main branch only)
- Merge is blocked if regression tests fail (set this in GitHub branch protection rules)

---

## One-Time Setup

### 1. Deploy OIDC + ECR

```bash
cd week10-cicd-regression

# Replace with your GitHub org and repo
make setup-oidc GITHUB_ORG=your-org GITHUB_REPO=warrantyai

# Copy the two outputs to GitHub Secrets:
# AWS_ROLE_ARN  → Settings → Secrets → Actions → New secret
# ECR_REGISTRY  → same
```

### 2. Enable GitHub OIDC provider

If the OIDC provider doesn't exist in your account yet, create it once:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 3. Set branch protection

In GitHub → Settings → Branches → Add rule for `main`:
- [x] Require status checks to pass before merging
- [x] Status check: `Prompt Regression Tests (20 fixtures · ≥ 90% accuracy)`

---

## What This Catches (and What It Doesn't)

**Catches:**
- Prompt edits that shift classification on known edge cases
- Model version changes that affect output structure or confidence
- Output parser bugs that break field extraction
- Accidental removal of prompt instructions that were doing real work

**Does not catch:**
- Brand-new edge cases not yet in fixtures (add them when you find them)
- Latency regressions (add a separate `test_latency.py` benchmark)
- Cost regressions from prompt bloat (add token counting)

---

## Cost

Each CI run invokes the Classifier for 20 documents using Haiku (with Sonnet fallback for low-confidence results).

| Scenario | Model calls | Est. cost |
|---|---|---|
| All 20 pass with Haiku | 20 × Haiku | ~$0.002 |
| 5 fall back to Sonnet | 15 × Haiku + 5 × Sonnet | ~$0.008 |

At ~10 PRs/week, regression tests cost **< $0.10/week**.

---

## Next Week (Week 11)

- Latency benchmark: `test_latency.py` — p95 < 8s per document
- Cost tracker: alert if token usage per document exceeds baseline by 20%
- Canary deploy: route 10% of traffic to new Lambda before full rollout
