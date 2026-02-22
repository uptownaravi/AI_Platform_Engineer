# Week 7 — WAF + Bedrock Guardrails + DevSecOps

**Theme:** Harden the warrantyAI system. Two-layer defense: perimeter blocking at the API gateway, semantic safety inside Bedrock.

---

## Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────┐
│  AWS WAF WebACL (REGIONAL)                  │  ← Layer 1: Perimeter
│                                             │
│  ├── Rule 1: Rate limit  100 req/5min/IP   │    Blocks bad traffic before
│  ├── Rule 2: CommonRuleSet (SQLi, XSS)     │    it touches your Lambda
│  ├── Rule 3: KnownBadInputsRuleSet         │    or Bedrock at all
│  └── Rule 4: IP Reputation List            │
└─────────────────┬───────────────────────────┘
                  │  (only clean traffic passes)
                  ▼
┌─────────────────────────────────────────────┐
│  API Gateway + Lambda                       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  Bedrock converse() + GovernanceShield      │  ← Layer 2: Semantic
│                                             │
│  ├── PII masking   Phone, Email, Address   │    Blocks harmful content
│  ├── Topic denial  Legal advice            │    even if WAF misses it
│  ├── Topic denial  Prompt injection        │    (e.g., subtle jailbreaks)
│  └── Content filter HATE/INSULTS/SEXUAL/   │
│                    VIOLENCE/MISCONDUCT/    │
│                    PROMPT_ATTACK — HIGH    │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  S3 Audit Log Bucket (SSE-AES256)           │  ← Compliance
│  warrantyai-audit-logs-{account-id}         │    
│  path: {agent}/YYYY/MM/DD/{uuid}.json       │    7-year retention
└─────────────────────────────────────────────┘
```

---

## What's in This Week

| File | Purpose |
|---|---|
| `main.tf` | WAF WebACL, Bedrock Guardrail, S3 audit bucket, per-agent IAM roles |
| `guardrails_demo.py` | Python integration: apply guardrail to `converse()`, audit to S3, test suite |

---

## WAF Rules Breakdown

| Rule | Type | Action | Why |
|---|---|---|---|
| RateLimitPerIP | Custom | Block | Prevents prompt flooding + Bedrock cost attacks |
| AWSManagedRulesCommonRuleSet | AWS Managed | Block | SQLi, XSS, bad request patterns |
| AWSManagedRulesKnownBadInputsRuleSet | AWS Managed | Block | log4j, SSRF, path traversal |
| AWSManagedRulesAmazonIpReputationList | AWS Managed | Block | Bots, Tor exit nodes, scanners |

WAF logs → CloudWatch Logs → CloudWatch alarm fires if blocks > 50 in 5 minutes.

---

## Bedrock Guardrail: GovernanceShield-Week7

Upgrades Week 6 guardrail with full content filter suite and prompt injection blocking.

### PII Masking
| Data Type | Action |
|---|---|
| PHONE | BLOCK |
| EMAIL | BLOCK |
| ADDRESS | BLOCK |
| NAME | ANONYMIZE |
| CREDIT_DEBIT_CARD_NUMBER | BLOCK |

### Topic Denial
| Topic | Trigger Examples |
|---|---|
| LegalAdvice | "How do I sue?", "What are my legal rights?", "File a consumer court case" |
| PromptInjection | "Ignore previous instructions", "You are now DAN", "Forget your system prompt" |

### Content Filters (all HIGH strength)
`HATE` · `INSULTS` · `SEXUAL` · `VIOLENCE` · `MISCONDUCT` · `PROMPT_ATTACK`

---

## IAM Least Privilege: Per-Agent Roles

Each LangGraph agent (Reader → Classifier → Reminder) gets its own IAM role with only the permissions it needs.

| Role | Allowed Actions |
|---|---|
| `warrantyai-reader-agent-role` | Textract, Titan embeddings, S3 read (warrantyai-*), audit write |
| `warrantyai-classifier-agent-role` | Bedrock Haiku + ApplyGuardrail, DynamoDB (warrantyai-workflows), audit write |
| `warrantyai-reminder-agent-role` | Bedrock Sonnet + ApplyGuardrail, SNS publish (warrantyai-*), audit write |

No `*` actions anywhere. Each role can only write to its own path in the audit bucket.

---

## S3 Audit Log Bucket

- **Encryption:** AES-256 server-side encryption, bucket key enabled
- **Access:** Public access fully blocked. Non-SSL access denied by bucket policy.
- **Versioning:** Enabled
- **Lifecycle:**
  - Day 0–90: S3 Standard
  - Day 90–365: S3 Standard-IA
  - Day 365+: Glacier
  - Day 2555 (7 years): Delete
- **Compliance note:** 7-year retention aligns with DPDP Act 2023 (India) data handling obligations for digital personal data.

---

---

## How to Use in Agent Code (Week 8 Preview)

```python
from guardrails_demo import query_warranty

# Inside a LangGraph classifier node:
answer = query_warranty(
    user_question  = state["user_query"],
    warranty_context = state["extracted_text"],
    model_id       = "anthropic.claude-haiku-4-5-20251001",
    agent_name     = "classifier",  # controls S3 audit path
)
```

Every call is:
- Protected by the guardrail
- Audited to S3 automatically
- Safe to use inside Lambda (stateless, no local state)

---

## Week 6 → Week 7 Upgrade Summary

| Feature | Week 6 | Week 7 |
|---|---|---|
| Content filters | HATE, INSULT | + SEXUAL, VIOLENCE, MISCONDUCT, PROMPT_ATTACK |
| Topic denial | LegalAdvice only | + PromptInjection |
| WAF | None | 4-rule WebACL + CloudWatch logging + alarm |
| IAM | Shared role | Per-agent least-privilege roles |
| Audit log | None | S3 bucket, SSE, 7-year retention, DPDP compliant |
| Python integration | None | guardrails_demo.py with 5-test security suite |

---

*warrantyAI · Week 7 · Building AI Platform Engineering · AWS Bedrock · LangGraph*
