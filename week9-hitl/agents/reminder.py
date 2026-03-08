"""
warrantyAI — Week 9
Reminder Agent (unchanged from Week 8)

Responsibilities:
  1. Read expiry_date + risk_level + structured_data from state
  2. Generate human-readable notification message via Bedrock Haiku
  3. Publish to SNS topic
  4. Write notification_sent, notification_message, sns_message_id to state
  5. Append audit entry to state

Week 9 note: This agent is called in two paths:
  - Normal flow: after HITL skips (non-high risk)
  - Resume flow: after human approves (run_from_reminder in run.py)

SNS topic: warrantyai-notifications (created by Week 8 Terraform)
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone, date
from state import WarrantyState

logger = logging.getLogger(__name__)

# ── AWS clients (warrantyai-reminder-agent-role from Week 7) ─────────────
bedrock = boto3.client("bedrock-runtime", region_name="ap-south-1")
sns     = boto3.client("sns", region_name="ap-south-1")
s3      = boto3.client("s3", region_name="ap-south-1")

AUDIT_BUCKET  = "warrantyai-audit-logs"
SNS_TOPIC_ARN = os.environ.get("WARRANTY_SNS_TOPIC_ARN", "")

REMINDER_PROMPT = """You are a warranty management assistant.

Write a clear, friendly warranty expiry notification for the customer.
Keep it under 3 sentences. Include the product name, expiry date, and one action they should take.

Warranty details:
- Product: {product_name}
- Brand: {brand}
- Expiry date: {expiry_date}
- Risk level: {risk_level}
- Days until expiry: {days_until_expiry}

Return ONLY the notification message text, no JSON, no formatting.
"""


def days_until_expiry(expiry_date_str: str) -> int:
    """Calculate days between today and expiry date."""
    try:
        expiry = date.fromisoformat(expiry_date_str)
        today  = date.today()
        return (expiry - today).days
    except Exception:
        return -1


def generate_notification_message(
    structured_data: dict,
    expiry_date: str,
    risk_level: str
) -> str:
    """Generate notification text via Bedrock Haiku."""
    days_left = days_until_expiry(expiry_date)

    prompt = REMINDER_PROMPT.format(
        product_name=structured_data.get("product_name", "your product"),
        brand=structured_data.get("brand", ""),
        expiry_date=expiry_date,
        risk_level=risk_level,
        days_until_expiry=days_left if days_left >= 0 else "unknown"
    )

    response = bedrock.invoke_model(
        modelId="anthropic.claude-haiku-4-5-20251001",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": prompt}]
        })
    )

    body = json.loads(response["body"].read())
    return body["content"][0]["text"].strip()


def publish_to_sns(
    message: str,
    document_id: str,
    tenant_id: str,
    risk_level: str,
    expiry_date: str
) -> str:
    """
    Publish notification to SNS topic.
    Returns SNS MessageId.
    """
    if not SNS_TOPIC_ARN:
        raise ValueError("WARRANTY_SNS_TOPIC_ARN env var not set")

    response = sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=message,
        Subject=f"[warrantyAI] Warranty Expiry Alert — {risk_level.upper()} Risk",
        MessageAttributes={
            "document_id": {
                "DataType": "String",
                "StringValue": document_id
            },
            "tenant_id": {
                "DataType": "String",
                "StringValue": tenant_id
            },
            "risk_level": {
                "DataType": "String",
                "StringValue": risk_level
            },
            "expiry_date": {
                "DataType": "String",
                "StringValue": expiry_date
            }
        }
    )
    return response["MessageId"]


def write_audit(document_id: str, tenant_id: str, status: str, detail: dict):
    """Write reminder audit entry to S3."""
    now = datetime.now(timezone.utc)
    key = f"reminder/{now.strftime('%Y/%m/%d')}/{document_id}.json"
    entry = {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "agent": "reminder",
        "status": status,
        "timestamp": now.isoformat(),
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

def reminder_agent(state: WarrantyState) -> dict:
    """
    LangGraph node function.
    Generates and publishes warranty expiry notification.
    Only sends if risk_level is medium or high.
    Low risk: logs but does not publish.
    """
    document_id     = state["document_id"]
    tenant_id       = state["tenant_id"]
    expiry_date     = state.get("expiry_date")
    risk_level      = state.get("risk_level")
    structured_data = state.get("structured_data") or {}

    errors    = list(state.get("errors", []))
    audit_log = list(state.get("audit_log", []))

    # If Classifier failed, nothing to remind about
    if not expiry_date or not risk_level:
        logger.warning("[Reminder] No expiry_date or risk_level in state — skipping")
        errors.append("reminder_agent: skipped — no classifier output")
        return {
            "notification_sent": False,
            "notification_message": None,
            "sns_message_id": None,
            "audit_log": audit_log,
            "errors": errors,
        }

    logger.info(
        f"[Reminder] Starting — document_id={document_id} "
        f"risk={risk_level} expiry={expiry_date}"
    )

    try:
        # ── Generate message ──────────────────────────────────────────────
        message = generate_notification_message(structured_data, expiry_date, risk_level)
        logger.info(f"[Reminder] Message generated: {message[:80]}...")

        # ── Publish logic: medium + high only ────────────────────────────
        if risk_level in ("medium", "high"):
            sns_message_id = publish_to_sns(
                message, document_id, tenant_id, risk_level, expiry_date
            )
            notification_sent = True
            logger.info(f"[Reminder] SNS published — MessageId={sns_message_id}")
        else:
            # Low risk — generate message but don't publish
            sns_message_id    = None
            notification_sent = False
            logger.info("[Reminder] Low risk — message generated but not published")

        # ── Audit ─────────────────────────────────────────────────────────
        audit_entry = write_audit(
            document_id, tenant_id, "success",
            {
                "risk_level": risk_level,
                "expiry_date": expiry_date,
                "days_until_expiry": days_until_expiry(expiry_date),
                "notification_sent": notification_sent,
                "sns_message_id": sns_message_id,
                "message_preview": message[:100]
            }
        )
        audit_log.append(audit_entry)

        return {
            "notification_sent": notification_sent,
            "notification_message": message,
            "sns_message_id": sns_message_id,
            "audit_log": audit_log,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"[Reminder] Failed: {e}")
        errors.append(f"reminder_agent: {str(e)}")

        audit_entry = write_audit(
            document_id, tenant_id, "error",
            {"error": str(e), "expiry_date": expiry_date}
        )
        audit_log.append(audit_entry)

        return {
            "notification_sent": False,
            "notification_message": None,
            "sns_message_id": None,
            "audit_log": audit_log,
            "errors": errors,
        }
