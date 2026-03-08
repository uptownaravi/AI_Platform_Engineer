"""
warrantyAI — Week 9
resume.py — Lambda handler for approve/reject link clicks

Flow:
  Reviewer clicks link in email
  → API Gateway GET /approve/{document_id} or /reject/{document_id}
  → This Lambda
  → Read state from DynamoDB
  → Update status: approved | rejected
  → If approved:  re-invoke the warrantyAI pipeline from reminder_agent
  → If rejected:  send SNS notification to tenant, write audit, stop

API Gateway routes (defined in infra/dynamodb.tf):
  GET /approve/{document_id}
  GET /reject/{document_id}
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone
from state import WarrantyState

logger = logging.getLogger(__name__)

# ── AWS clients ───────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
sns      = boto3.client("sns",        region_name="ap-south-1")
lambda_  = boto3.client("lambda",     region_name="ap-south-1")
s3       = boto3.client("s3",         region_name="ap-south-1")

HITL_TABLE           = os.environ.get("HITL_TABLE_NAME",       "warrantyai-hitl-queue")
TENANT_SNS_TOPIC_ARN = os.environ.get("WARRANTY_SNS_TOPIC_ARN", "")   # Week 8 topic
PIPELINE_LAMBDA_ARN  = os.environ.get("PIPELINE_LAMBDA_ARN",   "")    # warrantyAI run.py Lambda
AUDIT_BUCKET         = "warrantyai-audit-logs"


def get_review_record(document_id: str) -> dict:
    """Fetch the pending review record from DynamoDB."""
    table    = dynamodb.Table(HITL_TABLE)
    response = table.get_item(Key={"document_id": document_id, "sk": "REVIEW"})
    item     = response.get("Item")

    if not item:
        raise ValueError(f"No review record found for document_id={document_id}")
    if item.get("status") != "pending_review":
        raise ValueError(
            f"Review already actioned: status={item.get('status')} "
            f"document_id={document_id}"
        )
    return item


def update_review_status(document_id: str, status: str, reviewed_by: str) -> None:
    """Update DynamoDB record with reviewer decision."""
    table = dynamodb.Table(HITL_TABLE)
    table.update_item(
        Key={"document_id": document_id, "sk": "REVIEW"},
        UpdateExpression=(
            "SET #s = :status, reviewed_by = :reviewed_by, reviewed_at = :reviewed_at"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status":      status,
            ":reviewed_by": reviewed_by,
            ":reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    logger.info(f"[Resume] DynamoDB updated — document_id={document_id} status={status}")


def invoke_reminder_for_approved(warranty_state: WarrantyState) -> None:
    """
    Re-invoke the pipeline Lambda for an approved warranty.
    Passes the full state with hitl_status=approved so the graph
    skips reader/classifier/hitl and runs reminder_agent directly.
    """
    warranty_state["hitl_status"] = "approved"

    lambda_.invoke(
        FunctionName=PIPELINE_LAMBDA_ARN,
        InvocationType="Event",         # async — fire and forget
        Payload=json.dumps({
            "resume_from_hitl": True,
            "warranty_state":   warranty_state
        })
    )
    logger.info(
        f"[Resume] Pipeline re-invoked for approved warranty — "
        f"document_id={warranty_state['document_id']}"
    )


def notify_tenant_rejection(warranty_state: WarrantyState) -> None:
    """
    Send SNS notification to tenant that their warranty was reviewed
    and flagged — reminder will not be sent.
    """
    structured = warranty_state.get("structured_data") or {}
    message    = (
        f"Your warranty document has been reviewed by our team.\n\n"
        f"Product     : {structured.get('product_name', 'Unknown')}\n"
        f"Expiry Date : {warranty_state.get('expiry_date', 'Unknown')}\n\n"
        f"Our review found this warranty requires further verification "
        f"before a reminder can be issued. "
        f"Please contact support with your document ID: "
        f"{warranty_state['document_id']}"
    )

    sns.publish(
        TopicArn=TENANT_SNS_TOPIC_ARN,
        Subject="[warrantyAI] Your Warranty Document — Review Update",
        Message=message,
        MessageAttributes={
            "document_id": {
                "DataType": "String",
                "StringValue": warranty_state["document_id"]
            },
            "tenant_id": {
                "DataType": "String",
                "StringValue": warranty_state["tenant_id"]
            },
            "event_type": {
                "DataType": "String",
                "StringValue": "warranty_rejected"
            }
        }
    )
    logger.info(
        f"[Resume] Rejection SNS sent to tenant — "
        f"document_id={warranty_state['document_id']}"
    )


def write_audit(document_id: str, tenant_id: str, action: str, detail: dict) -> None:
    """Write resume action audit entry to S3."""
    now = datetime.now(timezone.utc)
    key = f"hitl-resume/{now.strftime('%Y/%m/%d')}/{document_id}-{action}.json"
    entry = {
        "document_id": document_id,
        "tenant_id":   tenant_id,
        "agent":       "hitl_resume",
        "action":      action,
        "timestamp":   now.isoformat(),
        **detail
    }
    s3.put_object(
        Bucket=AUDIT_BUCKET,
        Key=key,
        Body=json.dumps(entry),
        ContentType="application/json"
    )


def html_response(status_code: int, title: str, message: str) -> dict:
    """Return a simple HTML page — shown in browser when reviewer clicks link."""
    body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>warrantyAI — {title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 80px auto; padding: 0 20px; }}
    h1   {{ color: {'#047857' if status_code == 200 else '#DC2626'}; }}
    p    {{ color: #374151; line-height: 1.6; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{message}</p>
  <p><small>warrantyAI · warrantyai.in</small></p>
</body>
</html>"""
    return {
        "statusCode": status_code,
        "headers":    {"Content-Type": "text/html"},
        "body":       body
    }


# ── Lambda handler ─────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    API Gateway event handler.

    Path parameters:
      action      = "approve" | "reject"
      document_id = the warranty document ID from the email link

    GET /approve/{document_id}
    GET /reject/{document_id}
    """
    path_params = event.get("pathParameters", {}) or {}
    document_id = path_params.get("document_id", "")
    action      = path_params.get("action", "")

    # Extract reviewer identity from query string (optional — just email for now)
    query_params = event.get("queryStringParameters", {}) or {}
    reviewed_by  = query_params.get("reviewer", "unknown")

    logger.info(f"[Resume] Received {action} for document_id={document_id}")

    if not document_id or action not in ("approve", "reject"):
        return html_response(
            400,
            "Invalid Request",
            "This link is invalid or malformed. Please contact support."
        )

    try:
        # ── Fetch and validate review record ─────────────────────────────
        record         = get_review_record(document_id)
        warranty_state = json.loads(record["warranty_state"])

        # ── Update DynamoDB ───────────────────────────────────────────────
        status = "approved" if action == "approve" else "rejected"
        update_review_status(document_id, status, reviewed_by)

        # ── Take action ───────────────────────────────────────────────────
        if action == "approve":
            invoke_reminder_for_approved(warranty_state)
            write_audit(document_id, warranty_state["tenant_id"], "approved", {
                "reviewed_by": reviewed_by
            })
            return html_response(
                200,
                "Warranty Approved",
                f"The warranty reminder for document <strong>{document_id[:8]}...</strong> "
                f"has been approved and will be sent to the tenant shortly."
            )

        else:  # reject
            notify_tenant_rejection(warranty_state)
            write_audit(document_id, warranty_state["tenant_id"], "rejected", {
                "reviewed_by": reviewed_by
            })
            return html_response(
                200,
                "Warranty Rejected",
                f"The warranty document <strong>{document_id[:8]}...</strong> "
                f"has been flagged. The tenant has been notified. No reminder will be sent."
            )

    except ValueError as e:
        logger.warning(f"[Resume] Validation error: {e}")
        return html_response(
            409,
            "Already Actioned",
            "This warranty has already been reviewed. No further action needed."
        )

    except Exception as e:
        logger.error(f"[Resume] Unexpected error: {e}")
        return html_response(
            500,
            "Something Went Wrong",
            "An error occurred processing your request. Please try again or contact support."
        )
