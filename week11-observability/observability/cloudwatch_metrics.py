"""
warrantyAI — Week 11
observability/cloudwatch_metrics.py

CloudWatch custom metric emitter for the Classifier agent.

Metrics emitted (namespace: WarrantyAI/Agent):
    ClassifierLatency   — wall-clock ms for run_classifier() (histogram)
    TokensUsed          — total input + output tokens per call (count)
    ModelFallback       — 1 if Sonnet was used, 0 if Haiku was sufficient (count)
    RiskLevelHigh       — 1 if risk_level == "high", else 0 (count)
    RiskLevelMedium     — 1 if risk_level == "medium", else 0 (count)
    RiskLevelLow        — 1 if risk_level == "low", else 0 (count)

Dimensions:
    AgentName   — always "classifier"
    TenantId    — tenant_id passed to run_classifier()

Why custom metrics instead of Lambda default metrics:
    Lambda gives you invocation count and duration, but not:
    - Which model was used (Haiku vs Sonnet fallback rate)
    - Token consumption per call (cost proxy)
    - Risk level distribution (business signal — % of high-risk documents trending up?)

Usage:
    from observability.cloudwatch_metrics import emit_classifier_metrics
    emit_classifier_metrics(result=result, latency_ms=312.4, tenant_id="tenant_01")

The function is wrapped in try/except so a CloudWatch API failure never breaks
the agent. Metrics are best-effort.
"""

import os
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_NAMESPACE  = "WarrantyAI/Agent"
_AGENT_NAME = "classifier"

# Initialise lazily so tests that don't set AWS credentials don't fail at import
_cloudwatch: boto3.client = None  # type: ignore


def _get_cloudwatch():
    global _cloudwatch
    if _cloudwatch is None:
        _cloudwatch = boto3.client(
            "cloudwatch",
            region_name=os.environ.get("AWS_REGION", "ap-south-1"),
        )
    return _cloudwatch


def emit_classifier_metrics(
    result: dict,
    latency_ms: float,
    tenant_id: str,
) -> None:
    """
    Emit CloudWatch custom metrics for a single run_classifier() call.

    Args:
        result:     The dict returned by run_classifier() — must contain
                    risk_level, model_used, and optionally usage.total_tokens
        latency_ms: Wall-clock time of the call in milliseconds
        tenant_id:  Tenant identifier (used as a CloudWatch dimension)

    Silently skips if EMIT_METRICS env var is not "true" (useful in tests).
    """
    if os.environ.get("EMIT_METRICS", "true").lower() != "true":
        return

    risk_level = result.get("risk_level", "unknown").lower()
    model_used = result.get("model_used", "haiku")
    total_tokens = result.get("usage", {}).get("total_tokens", 0)
    is_fallback = 1 if model_used == "sonnet" else 0

    dimensions = [
        {"Name": "AgentName", "Value": _AGENT_NAME},
        {"Name": "TenantId",  "Value": tenant_id},
    ]

    metric_data = [
        # Latency — use milliseconds so the alarm threshold is human-readable
        {
            "MetricName": "ClassifierLatency",
            "Dimensions": dimensions,
            "Value":      latency_ms,
            "Unit":       "Milliseconds",
        },
        # Token usage — proxy for cost (1M Haiku input tokens ≈ $0.25)
        {
            "MetricName": "TokensUsed",
            "Dimensions": dimensions,
            "Value":      float(total_tokens),
            "Unit":       "Count",
        },
        # Model fallback — 1 means Haiku was insufficient and Sonnet was used
        {
            "MetricName": "ModelFallback",
            "Dimensions": dimensions,
            "Value":      float(is_fallback),
            "Unit":       "Count",
        },
        # Risk level distribution — one metric per level, value is 1 or 0
        # Lets you build a CloudWatch stacked bar showing daily risk breakdown
        {
            "MetricName": "RiskLevelHigh",
            "Dimensions": dimensions,
            "Value":      1.0 if risk_level == "high" else 0.0,
            "Unit":       "Count",
        },
        {
            "MetricName": "RiskLevelMedium",
            "Dimensions": dimensions,
            "Value":      1.0 if risk_level == "medium" else 0.0,
            "Unit":       "Count",
        },
        {
            "MetricName": "RiskLevelLow",
            "Dimensions": dimensions,
            "Value":      1.0 if risk_level == "low" else 0.0,
            "Unit":       "Count",
        },
    ]

    try:
        _get_cloudwatch().put_metric_data(
            Namespace=_NAMESPACE,
            MetricData=metric_data,
        )
        logger.debug(
            f"[Metrics] emitted: latency={latency_ms:.0f}ms tokens={total_tokens} "
            f"model={model_used} risk={risk_level} tenant={tenant_id}"
        )
    except ClientError as e:
        # Metric emission must never break the agent — log and continue
        logger.warning(f"[Metrics] CloudWatch put_metric_data failed: {e}")
    except Exception as e:
        logger.warning(f"[Metrics] Unexpected error emitting metrics: {e}")
