"""
warrantyAI — Week 8
Reader Agent

Responsibilities:
  1. Pull warranty PDF from S3
  2. Extract raw text via Textract (sync for < 5 pages, async for larger)
  3. Call Bedrock (Haiku) to structure the raw text into named fields
  4. Write raw_text + structured_data back to WarrantyState
  5. Append audit entry to state
"""

import json
import time
import boto3
import logging
from datetime import datetime, timezone
from state import WarrantyState

logger = logging.getLogger(__name__)

# ── AWS clients (uses warrantyai-reader-agent-role from Week 7) ──────────
textract = boto3.client("textract", region_name="ap-south-1")
bedrock  = boto3.client("bedrock-runtime", region_name="ap-south-1")
s3       = boto3.client("s3", region_name="ap-south-1")

BUCKET_NAME  = "warrantyai-documents"
AUDIT_BUCKET = "warrantyai-audit-logs"

STRUCTURE_PROMPT = """You are a warranty document parser.
Extract the following fields from the warranty text below.
Return ONLY valid JSON with these exact keys:
{
  "product_name": "",
  "brand": "",
  "model_number": "",
  "purchase_date": "",
  "warranty_start_date": "",
  "warranty_end_date": "",
  "warranty_period_months": 0,
  "category": "",
  "coverage_type": "",
  "dealer_name": "",
  "serial_number": ""
}

Use null for any field not found. Dates must be ISO 8601 (YYYY-MM-DD).
Category must be one of: appliance, electronics, commercial, other.

WARRANTY TEXT:
{raw_text}
"""


def extract_text_textract(s3_key: str) -> str:
    """
    Sync Textract for documents < 5 pages.
    Falls back to async for larger documents.
    """
    bucket, key = BUCKET_NAME, s3_key

    try:
        response = textract.detect_document_text(
            Document={"S3Object": {"Bucket": bucket, "Name": key}}
        )
        blocks = response.get("Blocks", [])
        lines = [
            b["Text"] for b in blocks
            if b["BlockType"] == "LINE" and "Text" in b
        ]
        raw_text = "\n".join(lines)
        logger.info(f"Textract extracted {len(lines)} lines from {key}")
        return raw_text

    except textract.exceptions.UnsupportedDocumentException:
        logger.warning("Document too large for sync Textract — using async")
        return extract_text_textract_async(s3_key)


def extract_text_textract_async(s3_key: str) -> str:
    """Async Textract for multi-page documents."""
    job = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": BUCKET_NAME, "Name": s3_key}}
    )
    job_id = job["JobId"]
    logger.info(f"Async Textract job started: {job_id}")

    # Poll until complete (max 60s for Week 8)
    for _ in range(30):
        result = textract.get_document_text_detection(JobId=job_id)
        status = result["JobStatus"]
        if status == "SUCCEEDED":
            blocks = result.get("Blocks", [])
            lines = [
                b["Text"] for b in blocks
                if b["BlockType"] == "LINE" and "Text" in b
            ]
            return "\n".join(lines)
        elif status == "FAILED":
            raise RuntimeError(f"Textract async job failed: {job_id}")
        time.sleep(2)

    raise TimeoutError(f"Textract job timed out: {job_id}")


def structure_with_bedrock(raw_text: str) -> dict:
    """
    Send raw text to Bedrock Haiku for structured extraction.
    Returns parsed dict of warranty fields.
    """
    prompt = STRUCTURE_PROMPT.format(raw_text=raw_text[:4000])  # token safety

    response = bedrock.invoke_model(
        modelId="anthropic.claude-haiku-4-5-20251001",
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

    # Strip markdown fences if model adds them
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    return json.loads(content)


def write_audit(document_id: str, tenant_id: str, agent: str, status: str, detail: dict):
    """Write audit entry to S3 — same pattern as Week 7."""
    now = datetime.now(timezone.utc)
    key = f"{agent}/{now.strftime('%Y/%m/%d')}/{document_id}.json"
    entry = {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "agent": agent,
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

def reader_agent(state: WarrantyState) -> dict:
    """
    LangGraph node function.
    Receives full WarrantyState, returns partial update dict.
    """
    document_id = state["document_id"]
    s3_key      = state["s3_key"]
    tenant_id   = state["tenant_id"]

    logger.info(f"[Reader] Starting — document_id={document_id}")

    errors    = list(state.get("errors", []))
    audit_log = list(state.get("audit_log", []))

    try:
        # Step 1: Extract raw text
        raw_text = extract_text_textract(s3_key)

        # Step 2: Structure with Bedrock Haiku
        structured_data = structure_with_bedrock(raw_text)

        # Step 3: Audit
        audit_entry = write_audit(
            document_id, tenant_id, "reader", "success",
            {
                "s3_key": s3_key,
                "text_length": len(raw_text),
                "fields_extracted": list(structured_data.keys())
            }
        )
        audit_log.append(audit_entry)

        logger.info(f"[Reader] Complete — extracted {len(structured_data)} fields")

        return {
            "raw_text": raw_text,
            "structured_data": structured_data,
            "audit_log": audit_log,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"[Reader] Failed: {e}")
        errors.append(f"reader_agent: {str(e)}")

        audit_entry = write_audit(
            document_id, tenant_id, "reader", "error",
            {"error": str(e), "s3_key": s3_key}
        )
        audit_log.append(audit_entry)

        return {
            "raw_text": None,
            "structured_data": None,
            "audit_log": audit_log,
            "errors": errors,
        }
