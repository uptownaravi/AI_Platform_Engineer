"""
warrantyAI — Week 9
HITL Agent (Human-in-the-Loop)

Responsibilities:
  1. Check risk_level from Classifier output
  2. If risk_level == "high":
       a. Serialise full WarrantyState to DynamoDB (status: pending_review)
       b. Send SNS review email with approve/reject links
       c. Raise NodeInterrupt to pause the LangGraph pipeline
  3. If risk_level != "high":
       a. Set hitl_status = "skipped"
       b. Pass through to Reminder agent immediately

The graph resumes when resume_lambda is invoked via the approve/reject link.
Resume logic lives in resume.py — NOT in this file.
"""

import json
import os
import time
import boto3
import logging
from datetime import datetime, timezone
from langgraph.errors import NodeInterrupt
from state import WarrantyState

logger = logging.getLogger(__name__)

# ── AWS clients ───────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
sns      = boto3.client("sns",       region_name="ap-south-1")
s3       = boto3.client("s3",        region_name="ap-south-1")

HITL_TABLE       = os.environ.get("HITL_TABLE_NAME", "warrantyai-hitl-queue")
REVIEW_SNS_ARN   = os.environ.get("REVIEW_SNS_TOPIC_ARN", "")
AUDIT_BUCKET     = "warrantyai-audit-logs"
API_BASE_URL     = os.environ.get("HITL_API_BASE_URL", "")   # API GW invoke URL

TTL_DAYS         = 7


def build_review_email(state: WarrantyState, approve_url: str, reject_url: str) -> str:
    """Build the plain-text review email body."""
    structured = state.get("structured_data") or {}
    return f"""
warrantyAI — High Risk Warranty Review Required
================================================

Document ID : {state['document_id']}
Tenant      : {state['tenant_id']}

Product     : {structured.get('product_name', 'Unknown')}
Brand       : {structured.get('brand', 'Unknown')}
Expiry Date : {state.get('expiry_date', 'Unknown')}
Risk Level  : HIGH

AI Reasoning:
Category    : {state.get('category', 'Unknown')}
Model Used  : {state.get('model_used', 'Unknown')}

─────────────────────────────────────────────────────
Please review and take action:

  APPROVE (send reminder to tenant):
  {approve_url}

  REJECT (notify tenant, no reminder sent):
  {reject_url}

─────────────────────────────────────────────────────
This review request expires in {TTL_DAYS} days.
Powered by warrantyAI · warrantyai.in
""".strip()


def write_to_dynamodb(state: WarrantyState) -> None:
    """
    Serialise full WarrantyState to DynamoDB.
    PK: document_id / SK: "REVIEW"
    """
    table = dynamodb.Table(HITL_TABLE)
    ttl   = int(time.time()) + (TTL_DAYS * 86400)

    table.put_item(Item={
        "document_id":   state["document_id"],
        "sk":            "REVIEW",
        "tenant_id":     state["tenant_id"],
        "status":        "pending_review",
        "warranty_state": json.dumps(state, default=str),   # full state as JSON string
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "reviewed_by":   None,
        "reviewed_at":   None,
        "ttl":           ttl,
    })
    logger.info(f"[HITL] Written to DynamoDB — document_id={state['document_id']}")


def send_review_email(state: WarrantyState) -> None:
    """
    Publish SNS review notification with approve/reject links.
    Reviewer clicks link → API Gateway → resume_lambda → DynamoDB update → pipeline resumes.
    """
    doc_id      = state["document_id"]
    approve_url = f"{API_BASE_URL}/approve/{doc_id}"
    reject_url  = f"{API_BASE_URL}/reject/{doc_id}"

    message = build_review_email(state, approve_url, reject_url)

    sns.publish(
        TopicArn=REVIEW_SNS_ARN,
        Subject=f"[warrantyAI] High Risk Warranty — Review Required ({doc_id[:8]})",
        Message=message,
        MessageAttributes={
            "document_id": {"DataType": "String", "StringValue": doc_id},
            "tenant_id":   {"DataType": "String", "StringValue": state["tenant_id"]},
            "event_type":  {"DataType": "String", "StringValue": "hitl_review_required"},
        }
    )
    logger.info(f"[HITL] SNS review email sent — document_id={doc_id}")


def write_audit(document_id: str, tenant_id: str, status: str, detail: dict) -> dict:
    """Write HITL audit entry to S3."""
    now = datetime.now(timezone.utc)
    key = f"hitl/{now.strftime('%Y/%m/%d')}/{document_id}.json"
    entry = {
        "document_id": document_id,
        "tenant_id":   tenant_id,
        "agent":       "hitl",
        "status":      status,
        "timestamp":   now.isoformat(),
        **detail
    }
    s3.put_object(
        Bucket=AUDIT_BUCKET,
        Key=key,
        Body=json.dumps(entry),
        ContentType="application/json"
    )
    return entry


# ── Agent function ─────────────────────────────────────────────────────────

def hitl_agent(state: WarrantyState) -> dict:
    """
    LangGraph node function.

    HIGH risk  → pause pipeline (NodeInterrupt), write to DynamoDB, send SNS email.
    Other risk → set hitl_status = "skipped", pass through to Reminder.
    """
    document_id = state["document_id"]
    tenant_id   = state["tenant_id"]
    risk_level  = state.get("risk_level")

    errors    = list(state.get("errors", []))
    audit_log = list(state.get("audit_log", []))

    logger.info(f"[HITL] Checking risk — document_id={document_id} risk={risk_level}")

    # ── Non-high risk: skip HITL, pass straight through ──────────────────
    if risk_level != "high":
        logger.info(f"[HITL] risk={risk_level} — skipping human review")

        audit_entry = write_audit(document_id, tenant_id, "skipped", {
            "risk_level": risk_level,
            "reason": "Only high risk requires human review"
        })
        audit_log.append(audit_entry)

        return {
            "hitl_required": False,
            "hitl_status":   "skipped",
            "hitl_token":    None,
            "audit_log":     audit_log,
            "errors":        errors,
        }

    # ── High risk: pause pipeline ─────────────────────────────────────────
    logger.info(f"[HITL] HIGH risk detected — pausing pipeline for human review")

    try:
        # Step 1: Write full state to DynamoDB
        write_to_dynamodb(state)

        # Step 2: Send SNS review email
        send_review_email(state)

        # Step 3: Audit
        audit_entry = write_audit(document_id, tenant_id, "pending_review", {
            "risk_level":  risk_level,
            "expiry_date": state.get("expiry_date"),
            "category":    state.get("category"),
        })
        audit_log.append(audit_entry)

        # Step 4: Interrupt the graph — pipeline pauses here
        # resume_lambda will restart from this node after human decision
        raise NodeInterrupt(
            f"High risk warranty requires human review. "
            f"document_id={document_id} — reviewer notified via SNS."
        )

    except NodeInterrupt:
        # Re-raise — LangGraph catches this and pauses the graph
        raise

    except Exception as e:
        logger.error(f"[HITL] Failed: {e}")
        errors.append(f"hitl_agent: {str(e)}")

        audit_entry = write_audit(document_id, tenant_id, "error", {"error": str(e)})
        audit_log.append(audit_entry)

        # On HITL failure: fail safe — don't auto-send reminder
        return {
            "hitl_required": True,
            "hitl_status":   "error",
            "hitl_token":    document_id,
            "audit_log":     audit_log,
            "errors":        errors,
        }
r