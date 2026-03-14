"""
warrantyAI — Week 10
agents/classifier.py

Classifier agent with a public `run_classifier()` entry point used by
the regression test suite.

Public API:
    run_classifier(document_text: str, tenant_id: str) -> dict
        Returns: {risk_level, confidence, category, model_used}

Internal flow:
    1. Wrap document_text in a structured_data dict
    2. Attempt classification with Haiku (cost-efficient)
    3. If confidence < 0.7 → retry with Sonnet
    4. Return normalised result

Risk level rules (derived from prompt):
    high   — expiry within 90 days OR warranty_period < 6 months
    medium — 90–180 days until expiry
    low    — > 180 days until expiry
"""

import json
import os
import logging
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-south-1"))

HAIKU_MODEL_ID  = "anthropic.claude-haiku-4-5-20251001"
SONNET_MODEL_ID = "anthropic.claude-sonnet-4-6"

CLASSIFY_PROMPT = """You are a warranty risk classification system.

Read the warranty document text below and return ONLY valid JSON with these exact fields:
{{
  "category": "",
  "expiry_date": "",
  "risk_level": "",
  "confidence": 0.0,
  "reasoning": ""
}}

Rules:
- category: one of [appliance, electronics, commercial, vehicle, other]
- expiry_date: ISO 8601 date (YYYY-MM-DD). Derive from warranty end date or purchase date + warranty period.
- risk_level:
    "high"   if expiry is within 90 days from today, OR warranty period is less than 6 months total
    "medium" if expiry is 90 to 180 days from today
    "low"    if expiry is more than 180 days from today
- confidence: float 0.0–1.0. Use < 0.7 when key dates are ambiguous or missing.
- reasoning: one concise sentence explaining the risk level decision.

Today's date for reference: 2026-03-14

WARRANTY DOCUMENT TEXT:
{document_text}
"""


def _invoke_model(document_text: str, model_id: str) -> dict:
    """Call a Bedrock Claude model with the classification prompt."""
    prompt = CLASSIFY_PROMPT.format(document_text=document_text)
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

    # Strip markdown code fences if present
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1]
        if content.startswith("json"):
            content = content[4:]

    return json.loads(content.strip())


def run_classifier(document_text: str, tenant_id: str) -> dict:
    """
    Public entry point for the regression test suite.

    Args:
        document_text: Raw warranty document text (from fixture input)
        tenant_id:     Tenant identifier (used for audit context)

    Returns:
        {
            "risk_level":   "high" | "medium" | "low"
            "confidence":   float 0.0–1.0
            "category":     "appliance" | "electronics" | "commercial" | "vehicle" | "other"
            "expiry_date":  "YYYY-MM-DD" or None
            "model_used":   "haiku" | "sonnet"
            "reasoning":    str
        }
    """
    logger.info(f"[Classifier] run_classifier — tenant_id={tenant_id}")

    # ── Attempt 1: Haiku ──────────────────────────────────────────────────────
    result     = _invoke_model(document_text, HAIKU_MODEL_ID)
    model_used = "haiku"
    confidence = result.get("confidence", 0.0)

    # ── Fallback: Sonnet if low confidence ────────────────────────────────────
    if confidence < 0.7:
        logger.info(f"[Classifier] Haiku confidence={confidence:.2f} < 0.7 — retrying with Sonnet")
        result     = _invoke_model(document_text, SONNET_MODEL_ID)
        model_used = "sonnet"

    logger.info(
        f"[Classifier] risk_level={result.get('risk_level')} "
        f"confidence={result.get('confidence'):.2f} model={model_used}"
    )

    return {
        "risk_level":  result.get("risk_level", "").lower(),
        "confidence":  result.get("confidence", 0.0),
        "category":    result.get("category", "other"),
        "expiry_date": result.get("expiry_date"),
        "model_used":  model_used,
        "reasoning":   result.get("reasoning", ""),
    }
