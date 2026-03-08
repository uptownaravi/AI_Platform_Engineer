"""
warrantyAI — Week 9
run.py — Entry point, updated for HITL resume path

Two invocation modes:
  1. Normal:      run_pipeline()         — full Reader → Classifier → HITL → Reminder
  2. HITL resume: run_from_reminder()    — skips to Reminder with approved state
                                           (called by resume_lambda after human approves)

Lambda handler routes between these two modes based on the event payload.
"""

import json
import logging
import uuid
from graph import app
from state import WarrantyState
from agents.reminder import reminder_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# Thread ID for MemorySaver checkpointer — one per document
def thread_config(document_id: str) -> dict:
    return {"configurable": {"thread_id": document_id}}


def run_pipeline(document_id: str, s3_key: str, tenant_id: str) -> WarrantyState:
    """
    Full pipeline: Reader → Classifier → HITL → (Reminder or pause).
    If HITL pauses the graph, returns state with hitl_status="pending_review".
    """
    initial_state: WarrantyState = {
        "document_id":         document_id,
        "s3_key":              s3_key,
        "tenant_id":           tenant_id,
        "raw_text":            None,
        "structured_data":     None,
        "category":            None,
        "expiry_date":         None,
        "risk_level":          None,
        "model_used":          None,
        "guardrail_triggered": None,
        "hitl_required":       None,
        "hitl_status":         None,
        "hitl_token":          None,
        "reviewed_by":         None,
        "reviewed_at":         None,
        "notification_sent":   None,
        "notification_message": None,
        "sns_message_id":      None,
        "audit_log":           [],
        "errors":              [],
    }

    logger.info(f"Pipeline starting — document_id={document_id}")
    config = thread_config(document_id)

    final_state = app.invoke(initial_state, config=config)

    hitl_status = final_state.get("hitl_status")
    logger.info(
        f"Pipeline result — document_id={document_id} "
        f"hitl_status={hitl_status} "
        f"risk={final_state.get('risk_level')} "
        f"notified={final_state.get('notification_sent')}"
    )
    return final_state


def run_from_reminder(warranty_state: WarrantyState) -> WarrantyState:
    """
    Resume path: called by resume_lambda after human approves a paused document.
    Runs only the Reminder agent — skips Reader, Classifier, HITL entirely.
    """
    document_id = warranty_state["document_id"]
    logger.info(f"Resume path: running Reminder only — document_id={document_id}")

    reminder_update = reminder_agent(warranty_state)
    warranty_state.update(reminder_update)

    logger.info(
        f"Resume complete — document_id={document_id} "
        f"notified={warranty_state.get('notification_sent')}"
    )
    return warranty_state


def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda entry point.

    Normal invocation (S3 trigger):
      event.Records[*].s3.object.key

    HITL resume invocation (from resume_lambda):
      event.resume_from_hitl = True
      event.warranty_state   = <full WarrantyState dict>
    """
    # ── HITL resume path ─────────────────────────────────────────────────
    if event.get("resume_from_hitl"):
        warranty_state = event["warranty_state"]
        final_state    = run_from_reminder(warranty_state)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "document_id":       final_state.get("document_id"),
                "notification_sent": final_state.get("notification_sent"),
                "sns_message_id":    final_state.get("sns_message_id"),
                "errors":            final_state.get("errors"),
            })
        }

    # ── Normal S3 trigger path ────────────────────────────────────────────
    results = []
    for record in event.get("Records", []):
        s3_key    = record["s3"]["object"]["key"]
        parts     = s3_key.split("/")
        tenant_id = parts[1] if len(parts) >= 3 else "unknown"
        doc_id    = str(uuid.uuid4())

        final_state = run_pipeline(doc_id, s3_key, tenant_id)
        results.append({
            "document_id":       doc_id,
            "s3_key":            s3_key,
            "risk_level":        final_state.get("risk_level"),
            "hitl_status":       final_state.get("hitl_status"),
            "notification_sent": final_state.get("notification_sent"),
            "errors":            final_state.get("errors"),
        })

    return {"statusCode": 200, "body": json.dumps(results)}


if __name__ == "__main__":
    # ── Local test ────────────────────────────────────────────────────────
    result = run_pipeline(
        document_id="test-week9-001",
        s3_key="tenants/t001/sample-warranty.pdf",
        tenant_id="t001"
    )

    print("\n── Final State ──────────────────────────────────────────")
    print(f"Risk Level:         {result.get('risk_level')}")
    print(f"HITL Required:      {result.get('hitl_required')}")
    print(f"HITL Status:        {result.get('hitl_status')}")
    print(f"Notification Sent:  {result.get('notification_sent')}")
    print(f"Errors:             {result.get('errors')}")
    print(f"Audit entries:      {len(result.get('audit_log', []))}")
