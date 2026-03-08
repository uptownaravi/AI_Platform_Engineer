# warrantyAI — Week 9: Human-in-the-Loop

Week 9 inserts a **Human-in-the-Loop (HITL) pause node** between the Classifier and Reminder agents. When a warranty is classified as **high risk**, the pipeline stops, emails a reviewer with approve/reject links, and only continues when a human acts.

## What Changed from Week 8

| Component | Week 8 | Week 9 |
|---|---|---|
| Graph nodes | Reader → Classifier → Reminder | Reader → Classifier → **HITL** → Reminder |
| Lambda functions | 1 (pipeline) | 2 (pipeline + **resume**) |
| DynamoDB | Workflow metadata only | + **HITL queue** (`warrantyai-hitl-queue`) |
| API Gateway | None | **HTTP API** with approve/reject routes |
| WarrantyState | 15 fields | +5 HITL fields |

## Flow

```
S3 Upload (tenants/*.pdf)
    │
    ▼
Reader → Classifier → HITL Agent
                          │
           risk != high   │   risk == high
                          │
              ┌───────────┤
              │           │
              ▼           ▼
         Reminder    DynamoDB (pending_review)
         (direct)    SNS → Reviewer email
                          │
                    [Human clicks link]
                          │
                    API Gateway
                    /approve/{doc_id}  OR  /reject/{doc_id}
                          │
              ┌───────────┴──────────────┐
              ▼                          ▼
         APPROVE:                   REJECT:
         Update DynamoDB            Update DynamoDB
         Invoke pipeline            SNS to tenant
         resume_from_hitl=True      (no reminder)
              │
              ▼
         Reminder → SNS to tenant
```

## New Files This Week

| File | Purpose |
|---|---|
| `agents/hitl.py` | HITL LangGraph node — DynamoDB write + SNS email + NodeInterrupt |
| `resume.py` | Lambda handler for approve/reject API Gateway routes |
| `infra/dynamodb.tf` | DynamoDB table + API Gateway HTTP API |

## Updated Files

| File | Change |
|---|---|
| `state.py` | +5 HITL fields (hitl_required, hitl_status, hitl_token, reviewed_by, reviewed_at) |
| `graph.py` | Added hitl node + MemorySaver checkpointer + interrupt_before=["hitl"] |
| `run.py` | Two invocation modes: normal S3 trigger + HITL resume path |

## Deploy

```bash
# Standalone week9 deployment (requires existing Week 8 pipeline Lambda)
make build-layer
make deploy \
  EMAIL=tenant@example.com \
  REVIEWER_EMAIL=reviewer@example.com \
  RESUME_LAMBDA_ARN=arn:aws:lambda:... \
  PIPELINE_LAMBDA_ARN=arn:aws:lambda:...
```

For the full stack (Weeks 1-9), use `warrantyAI/` instead — the consolidated folder handles all resources.

## DynamoDB Schema

Table: `warrantyai-hitl-queue`

| Field | Type | Notes |
|---|---|---|
| `document_id` | PK (S) | |
| `sk` | SK (S) | Always `"REVIEW"` |
| `tenant_id` | S | |
| `status` | S | `pending_review` / `approved` / `rejected` |
| `warranty_state` | S | Full WarrantyState as JSON string |
| `created_at` | S | ISO 8601 |
| `reviewed_by` | S | nullable |
| `reviewed_at` | S | nullable |
| `ttl` | N | Auto-expires after 7 days |

## Known Gaps (Week 10 Backlog)

- `MemorySaver` is in-memory only — state lost on Lambda cold start. Week 10 swaps for DynamoDB checkpointer.
- `reviewed_by` populated from `?reviewer=email` query param — no auth. Week 10 adds Cognito.
- No retry if `invoke_reminder_for_approved()` fails — silent failure. Week 10 adds SQS DLQ.
