"""
warrantyAI — Week 11
agents/classifier.py

Extends the Week 10 Classifier with:
  1. LangSmith @traceable — every call is traced in the LangSmith UI when
     LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY is set
  2. CloudWatch custom metrics — latency, token usage, model fallback, risk level
  3. Token usage extraction — Bedrock response includes usage.input/output_tokens;
     now returned in the result dict under "usage" key

Public API (unchanged from Week 10):
    run_classifier(document_text: str, tenant_id: str) -> dict

The returned dict now includes an additional "usage" key:
    {
        "risk_level":   "high" | "medium" | "low",
        "confidence":   float,
        "category":     str,
        "expiry_date":  str | None,
        "model_used":   "haiku" | "sonnet",
        "reasoning":    str,
        "usage": {
            "input_tokens":  int,
            "output_tokens": int,
            "total_tokens":  int,
        }
    }
"""

import json
import os
import time
import logging
import boto3

from observability.langsmith_tracer import traceable, build_run_metadata, truncate_for_trace
from observability.cloudwatch_metrics import emit_classifier_metrics

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


def _invoke_model(document_text: str, model_id: str) -> tuple[dict, dict]:
    """
    Call a Bedrock Claude model with the classification prompt.

    Returns:
        (result_dict, usage_dict)
        usage_dict = {"input_tokens": int, "output_tokens": int, "total_tokens": int}
    """
    prompt   = CLASSIFY_PROMPT.format(document_text=document_text)
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
    body    = json.loads(response["body"].read())
    content = body["content"][0]["text"].strip()

    # Extract token usage from Bedrock response
    raw_usage    = body.get("usage", {})
    input_tokens  = raw_usage.get("input_tokens", 0)
    output_tokens = raw_usage.get("output_tokens", 0)
    usage = {
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "total_tokens":  input_tokens + output_tokens,
    }

    # Strip markdown code fences if present
    if content.startswith("```"):
        parts   = content.split("```")
        content = parts[1]
        if content.startswith("json"):
            content = content[4:]

    return json.loads(content.strip()), usage


@traceable(
    name="classifier",
    run_type="chain",
    metadata=build_run_metadata(),
)
def run_classifier(document_text: str, tenant_id: str) -> dict:
    """
    Classify a warranty document and return risk assessment.

    LangSmith traces this function automatically when tracing is enabled.
    CloudWatch metrics are emitted after every call.

    Args:
        document_text: Raw warranty document text
        tenant_id:     Tenant identifier for multi-tenant isolation

    Returns:
        {
            risk_level, confidence, category, expiry_date,
            model_used, reasoning, usage
        }
    """
    logger.info(f"[Classifier] run_classifier — tenant_id={tenant_id}")
    t_start = time.monotonic()

    #    Attempt 1: Haiku                                                       
    result, usage  = _invoke_model(document_text, HAIKU_MODEL_ID)
    model_used     = "haiku"
    confidence     = result.get("confidence", 0.0)

    #    Fallback: Sonnet if low confidence                                     
    if confidence < 0.7:
        logger.info(f"[Classifier] Haiku confidence={confidence:.2f} < 0.7 — retrying with Sonnet")
        result, sonnet_usage = _invoke_model(document_text, SONNET_MODEL_ID)
        model_used = "sonnet"
        # Accumulate tokens across both calls (Haiku attempt + Sonnet retry)
        usage = {
            "input_tokens":  usage["input_tokens"]  + sonnet_usage["input_tokens"],
            "output_tokens": usage["output_tokens"] + sonnet_usage["output_tokens"],
            "total_tokens":  usage["total_tokens"]  + sonnet_usage["total_tokens"],
        }

    latency_ms = (time.monotonic() - t_start) * 1000

    logger.info(
        f"[Classifier] risk_level={result.get('risk_level')} "
        f"confidence={result.get('confidence', 0):.2f} model={model_used} "
        f"tokens={usage['total_tokens']} latency={latency_ms:.0f}ms"
    )

    output = {
        "risk_level":  result.get("risk_level", "").lower(),
        "confidence":  result.get("confidence", 0.0),
        "category":    result.get("category", "other"),
        "expiry_date": result.get("expiry_date"),
        "model_used":  model_used,
        "reasoning":   result.get("reasoning", ""),
        "usage":       usage,
    }

    # Emit CloudWatch metrics (best-effort — failure never raises)
    emit_classifier_metrics(
        result=output,
        latency_ms=latency_ms,
        tenant_id=tenant_id,
    )

    return output
