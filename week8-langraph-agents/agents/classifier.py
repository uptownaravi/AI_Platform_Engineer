"""
warrantyAI — Week 8
Classifier Agent

Responsibilities:
  1. Read structured_data from state (set by Reader agent)
  2. Attempt classification with Haiku (cost-efficient)
  3. If Haiku fails or returns low-confidence → retry with Sonnet
  4. Apply GovernanceShield-Week7 guardrail via Week 7 wrapper
  5. Write category, expiry_date, risk_level, model_used to state
  6. Append audit entry to state

Week 7 connection:
  - Imports invoke_with_guardrail() and write_audit_log() from guardrails_demo.py
  - Uses warrantyai-classifier-agent-role IAM (already exists)
  - GovernanceShield-Week7 guardrail ID referenced via env var
"""

import json
import os
import sys
import boto3
import logging
from datetime import datetime, timezone
from state import WarrantyState

# Import Week 7 guardrail wrappers
# guardrails_demo.py lives in week7-waf-guardrails/
sys.path.append(os.path.join(os.path.dirname(__file__), "../../week7-waf-guardrails"))
try:
    from guardrails_demo import invoke_with_guardrail, write_audit_log as guardrail_audit
    GUARDRAILS_AVAILABLE = True
except ImportError:
    GUARDRAILS_AVAILABLE = False
    logging.warning("[Classifier] Week 7 guardrails_demo not found — running without guardrails")

logger = logging.getLogger(__name__)

# AWS clients (warrantyai-classifier-agent-role)
bedrock  = boto3.client("bedrock-runtime", region_name="ap-south-1")
s3       = boto3.client("s3", region_name="ap-south-1")

AUDIT_BUCKET    = "warrantyai-audit-logs"
GUARDRAIL_ID    = os.environ.get("GOVERNANCESHIELD_ID", "")   # Set from Week 7 Terraform output
GUARDRAIL_VER   = os.environ.get("GOVERNANCESHIELD_VERSION", "DRAFT")

HAIKU_MODEL_ID  = "anthropic.claude-haiku-4-5-20251001"
SONNET_MODEL_ID = "anthropic.claude-sonnet-4-6"

CLASSIFY_PROMPT = """You are a warranty classification system.

Given the structured warranty data below, return ONLY valid JSON with these exact fields:
{{
  "category": "",
  "expiry_date": "",
  "risk_level": "",
  "confidence": 0.0,
  "reasoning": ""
}}

Rules:
- category: one of [appliance, electronics, commercial, other]
- expiry_date: ISO 8601 date (YYYY-MM-DD). Derive from warranty_end_date or purchase_date + warranty_period_months.
- risk_level: "high" if expiry within 90 days or warranty_period < 6 months, "medium" if 90-180 days, "low" otherwise
- confidence: float 0.0-1.0. If < 0.7, the system will retry with a more powerful model.
- reasoning: one sentence explaining the risk level

WARRANTY DATA:
{structured_data}
"""


def classify_with_model(structured_data: dict, model_id: str) -> dict:
    """
    Run classification prompt against specified Bedrock model.
    Returns parsed classification dict.
    """
    prompt = CLASSIFY_PROMPT.format(
        structured_data=json.dumps(structured_data, indent=2)
    )

    if GUARDRAILS_AVAILABLE and GUARDRAIL_ID:
        # Use Week 7 guardrail wrapper
        response_text = invoke_with_guardrail(
            prompt=prompt,
            model_id=model_id,
            guardrail_id=GUARDRAIL_ID,
            guardrail_version=GUARDRAIL_VER
        )
        guardrail_triggered = response_text.get("blocked", False)
        content = response_text.get("text", "")
    else:
        # Direct invoke (no guardrails — dev/test only)
        response = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        body = json.loads(response["body"].read())
        content = body["content"][0]["text"].strip()
        guardrail_triggered = False

    # Strip markdown fences
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    result = json.loads(content)
    result["guardrail_triggered"] = guardrail_triggered
    return result


def write_audit(document_id: str, tenant_id: str, status: str, detail: dict):
    """Write classifier audit entry to S3."""
    now = datetime.now(timezone.utc)
    key = f"classifier/{now.strftime('%Y/%m/%d')}/{document_id}.json"
    entry = {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "agent": "classifier",
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


# Agent function

def classifier_agent(state: WarrantyState) -> dict:
    """
    LangGraph node function.
    Haiku-first classification with Sonnet fallback.
    Guardrail applied on every invocation.
    """
    document_id     = state["document_id"]
    tenant_id       = state["tenant_id"]
    structured_data = state.get("structured_data")

    errors    = list(state.get("errors", []))
    audit_log = list(state.get("audit_log", []))

    # If Reader failed, nothing to classify
    if not structured_data:
        logger.warning(f"[Classifier] No structured_data in state — skipping")
        errors.append("classifier_agent: skipped — no structured_data from reader")
        return {
            "category": None,
            "expiry_date": None,
            "risk_level": None,
            "model_used": None,
            "guardrail_triggered": False,
            "audit_log": audit_log,
            "errors": errors,
        }

    logger.info(f"[Classifier] Starting — document_id={document_id}")

    try:
        # Attempt 1: Haiku
        logger.info("[Classifier] Trying Haiku...")
        result     = classify_with_model(structured_data, HAIKU_MODEL_ID)
        model_used = "haiku"
        confidence = result.get("confidence", 0.0)

        # Fallback: Sonnet if confidence < 0.7
        if confidence < 0.7:
            logger.info(
                f"[Classifier] Haiku confidence {confidence:.2f} < 0.7 — retrying with Sonnet"
            )
            result     = classify_with_model(structured_data, SONNET_MODEL_ID)
            model_used = "sonnet"

        # Write audit
        audit_entry = write_audit(
            document_id, tenant_id, "success",
            {
                "model_used": model_used,
                "confidence": result.get("confidence"),
                "category": result.get("category"),
                "expiry_date": result.get("expiry_date"),
                "risk_level": result.get("risk_level"),
                "guardrail_triggered": result.get("guardrail_triggered", False),
                "reasoning": result.get("reasoning")
            }
        )
        audit_log.append(audit_entry)

        logger.info(
            f"[Classifier] Complete — category={result['category']} "
            f"risk={result['risk_level']} model={model_used}"
        )

        return {
            "category": result.get("category"),
            "expiry_date": result.get("expiry_date"),
            "risk_level": result.get("risk_level"),
            "model_used": model_used,
            "guardrail_triggered": result.get("guardrail_triggered", False),
            "audit_log": audit_log,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"[Classifier] Failed: {e}")
        errors.append(f"classifier_agent: {str(e)}")

        audit_entry = write_audit(
            document_id, tenant_id, "error",
            {"error": str(e)}
        )
        audit_log.append(audit_entry)

        return {
            "category": None,
            "expiry_date": None,
            "risk_level": None,
            "model_used": None,
            "guardrail_triggered": False,
            "audit_log": audit_log,
            "errors": errors,
        }
