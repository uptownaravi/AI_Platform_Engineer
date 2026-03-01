"""
warrantyAI — Week 8
run.py — Entry point for the LangGraph pipeline

Run locally:
    python run.py

Or invoke as a Lambda handler by calling:
    lambda_handler(event, context)
"""

import json
import logging
import uuid
from graph import app
from state import WarrantyState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def run_pipeline(document_id: str, s3_key: str, tenant_id: str) -> WarrantyState:
    """
    Invoke the full warrantyAI LangGraph pipeline.
    Returns the final WarrantyState after all 3 agents complete.
    """
    initial_state: WarrantyState = {
        # Input
        "document_id": document_id,
        "s3_key": s3_key,
        "tenant_id": tenant_id,

        # Reader (empty — to be filled)
        "raw_text": None,
        "structured_data": None,

        # Classifier (empty — to be filled)
        "category": None,
        "expiry_date": None,
        "risk_level": None,
        "model_used": None,
        "guardrail_triggered": None,

        # Reminder (empty — to be filled)
        "notification_sent": None,
        "notification_message": None,
        "sns_message_id": None,

        # Audit
        "audit_log": [],
        "errors": [],
    }

    logger.info(
        f"Pipeline starting — document_id={document_id} "
        f"tenant_id={tenant_id} s3_key={s3_key}"
    )

    final_state = app.invoke(initial_state)

    logger.info(
        f"Pipeline complete — "
        f"category={final_state.get('category')} "
        f"risk={final_state.get('risk_level')} "
        f"expiry={final_state.get('expiry_date')} "
        f"notified={final_state.get('notification_sent')} "
        f"errors={final_state.get('errors')}"
    )

    return final_state


def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda entry point.
    Triggered by S3 event when a new warranty document is uploaded.

    Expected event format (S3 trigger):
    {
        "Records": [{
            "s3": {
                "bucket": {"name": "warrantyai-documents"},
                "object": {"key": "tenants/t001/doc123.pdf"}
            }
        }]
    }
    """
    results = []

    for record in event.get("Records", []):
        s3_key    = record["s3"]["object"]["key"]
        # Extract tenant_id from key prefix: "tenants/{tenant_id}/..."
        parts     = s3_key.split("/")
        tenant_id = parts[1] if len(parts) >= 3 else "unknown"
        doc_id    = str(uuid.uuid4())

        final_state = run_pipeline(doc_id, s3_key, tenant_id)
        results.append({
            "document_id":    doc_id,
            "s3_key":         s3_key,
            "category":       final_state.get("category"),
            "risk_level":     final_state.get("risk_level"),
            "expiry_date":    final_state.get("expiry_date"),
            "notification_sent": final_state.get("notification_sent"),
            "errors":         final_state.get("errors"),
        })

    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }


if __name__ == "__main__":
    #     Local test run                                                                               
    # Replace with a real S3 key from your warrantyai-documents bucket
    result = run_pipeline(
        document_id="test-doc-001",
        s3_key="tenants/t001/sample-warranty.pdf",
        tenant_id="t001"
    )

    print("\n    Final State                                                                ")
    print(f"Category:           {result.get('category')}")
    print(f"Expiry Date:        {result.get('expiry_date')}")
    print(f"Risk Level:         {result.get('risk_level')}")
    print(f"Model Used:         {result.get('model_used')}")
    print(f"Guardrail Hit:      {result.get('guardrail_triggered')}")
    print(f"Notification Sent:  {result.get('notification_sent')}")
    print(f"SNS Message ID:     {result.get('sns_message_id')}")
    print(f"Errors:             {result.get('errors')}")
    print(f"Audit entries:      {len(result.get('audit_log', []))}")
