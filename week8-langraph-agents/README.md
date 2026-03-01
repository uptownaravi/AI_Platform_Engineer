# warrantyAI — Week 8: LangGraph 3-Agent System

> **Theme:** Build the actual core of warrantyAI. The agents that do the work.

---

## What This Week Builds

A 3-agent LangGraph pipeline that processes any warranty PDF end-to-end:

```
S3 upload (PDF)
      │
      ▼
┌─────────────┐     raw_text          ┌───────────────┐     expiry_date     ┌─────────────────┐
│  Reader     │──────────────────────▶│  Classifier   │────────────────────▶│  Reminder       │
│  Agent      │     structured_data   │  Agent        │     risk_level      │  Agent          │
│             │                       │               │                     │                 │
│ Textract    │                       │ Haiku (fast)  │                     │ Haiku (draft)   │
│ + Haiku     │                       │ → Sonnet      │                     │ + SNS publish   │
│ (structure) │                       │   (fallback)  │                     │   (med/high)    │
└─────────────┘                       └───────────────┘                     └─────────────────┘
                                                                                     │
                                                                                     ▼
                                                                             warrantyai-notifications
                                                                             (SNS → email/SMS)
```

All Bedrock calls go through the **GovernanceShield-Week7** guardrail (PII masking + prompt injection block).
Every agent writes an audit entry to the **warrantyai-audit-logs** S3 bucket (DPDP compliant).

---

## Folder Structure

```
week8-langgraph-agents/
├── state.py            # WarrantyState TypedDict — shared contract between agents
├── graph.py            # LangGraph StateGraph: wires nodes + edges in 15 lines
├── run.py              # Entry point (local run + Lambda handler)
├── requirements.txt    # langgraph, langchain-core, boto3
├── Makefile            # build-layer / deploy / test / run-local
├── agents/
│   ├── reader.py       # Textract extraction + Bedrock structuring
│   ├── classifier.py   # Haiku-first classification (Sonnet fallback at confidence < 0.7)
│   └── reminder.py     # Expiry calc + SNS notification (medium/high risk only)
├── infra/
    ├── main.tf         # Lambda + IAM + S3 trigger + CloudWatch alarm
    ├── sns.tf          # SNS topic + email subscription
    ├── variables.tf    # All configurable inputs
    └── outputs.tf      # Lambda ARN, SNS ARN, log group
```

---

## Agent Responsibilities

| Agent | Model | Input from State | Output to State |
|---|---|---|---|
| **Reader** | Haiku (structure) | `s3_key` | `raw_text`, `structured_data` |
| **Classifier** | Haiku → Sonnet | `structured_data` | `category`, `expiry_date`, `risk_level` |
| **Reminder** | Haiku (message) | `expiry_date`, `risk_level` | `notification_sent`, `sns_message_id` |

---

## Week 7 Connections

- **Guardrails:** `classifier.py` imports `invoke_with_guardrail()` from `week7-waf-guardrails/guardrails_demo.py`
- **IAM roles:** `warrantyai-reader-agent-role`, `warrantyai-classifier-agent-role`, `warrantyai-reminder-agent-role` (created in `warrantyAI/infra/iam.tf`) — the pipeline Lambda uses a combined role
- **Audit bucket:** `warrantyai-audit-logs` (created in Week 7) receives audit entries from all 3 agents

---

## Prerequisites

- AWS CLI configured with `ap-south-1` access
- Weeks 1–7 deployed (`warrantyAI/infra/`)
- Guardrail ID from: `cd warrantyAI/infra && terraform output guardrail_id`
- Python 3.12 + pip

---

## Deploy

```bash
# 1. Build Lambda layer (LangGraph deps for linux/arm64)
make build-layer

# 2. Deploy SNS + Lambda + IAM + S3 trigger
make deploy \
  DOCS_BUCKET=warrantyai-documents \
  EMAIL=your@email.com
```

Set optional guardrail wiring:
```bash
make deploy \
  DOCS_BUCKET=warrantyai-documents \
  EMAIL=your@email.com \
  TF_VAR_governanceshield_guardrail_id=<id-from-week7-output> \
  TF_VAR_governanceshield_guardrail_version=1
```

---

---

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| LangGraph over raw chaining | StateGraph | State is auditable, edges are explicit, easy to add HITL node in Week 9 |
| Haiku-first + Sonnet fallback | Confidence threshold 0.7 | FinOps: Haiku is 5x cheaper. Fallback only when needed |
| Single Lambda | All 3 agents in one function | Simpler deployment; agents share in-memory state via LangGraph |
| ARM64 (Graviton) | `architectures = ["arm64"]` | 20% cheaper per invocation (Week 6 FinOps) |
| SNS for notifications | Medium + high risk only | Low-risk docs don't need immediate attention |

---

## What Week 9 Adds

Week 9 inserts a **Human-in-the-Loop** node between Classifier and Reminder:
```python
graph.add_edge("classifier", "hitl")       # pauses, saves to DynamoDB
graph.add_conditional_edges("hitl", route_on_approval)  # resumes on API call
graph.add_edge("hitl_approved", "reminder")
```
