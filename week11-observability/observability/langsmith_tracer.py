"""
warrantyAI — Week 11
observability/langsmith_tracer.py

LangSmith tracing for agent nodes.

Every call to run_classifier() is automatically traced when:
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=<your-langsmith-key>
    LANGCHAIN_PROJECT=warrantyai-production   (optional — defaults to "default")

When these env vars are absent, @traceable is a no-op. No code changes needed
between traced and un-traced runs.

What each trace captures:
    - Inputs: document_text (first 500 chars), tenant_id
    - Outputs: risk_level, confidence, category, model_used, token totals
    - Metadata: aws_region, function version, git sha
    - Latency: wall-clock time of the decorated function (LangSmith measures automatically)

Usage:
    from observability.langsmith_tracer import traceable, build_run_metadata

    @traceable(name="classifier", run_type="chain", metadata=build_run_metadata())
    def run_classifier(document_text, tenant_id):
        ...
"""

import os
import functools
import logging

logger = logging.getLogger(__name__)

#      Try to import LangSmith                                                                                                       
# If langsmith is not installed, provide a no-op @traceable so the rest of the
# code doesn't need to know whether tracing is active.

try:
    from langsmith import traceable as _traceable  # type: ignore
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False
    logger.debug("langsmith not installed — tracing disabled")


def traceable(name: str = "", run_type: str = "chain", metadata: dict | None = None):
    """
    Decorator factory that wraps a function with LangSmith tracing.

    When LANGCHAIN_TRACING_V2 != "true" or langsmith is not installed,
    returns the original function unchanged.

    Args:
        name:      Human-readable name shown in the LangSmith UI (e.g. "classifier")
        run_type:  LangSmith run type: "chain", "llm", "tool", "retriever"
        metadata:  Static metadata dict attached to every run

    Example:
        @traceable(name="classifier", run_type="chain", metadata=build_run_metadata())
        def run_classifier(document_text, tenant_id):
            ...
    """
    tracing_enabled = (
        _LANGSMITH_AVAILABLE
        and os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
        and os.environ.get("LANGCHAIN_API_KEY", "")
    )

    def decorator(fn):
        if not tracing_enabled:
            return fn
        return _traceable(
            name=name or fn.__name__,
            run_type=run_type,
            metadata=metadata or {},
        )(fn)

    return decorator


def build_run_metadata() -> dict:
    """
    Return static metadata attached to every LangSmith run.

    These fields show up in the LangSmith UI under "Metadata" and can be
    used to filter runs by environment, version, or region.
    """
    return {
        "service":          "warrantyai",
        "component":        "classifier",
        "aws_region":       os.environ.get("AWS_REGION", "ap-south-1"),
        "function_version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "local"),
        "git_sha":          os.environ.get("GIT_COMMIT", "unknown"),
        "environment":      os.environ.get("ENVIRONMENT", "development"),
    }


def truncate_for_trace(text: str, max_chars: int = 500) -> str:
    """
    Truncate document text before sending to LangSmith.

    LangSmith stores inputs in its cloud. Truncate to avoid sending full
    warranty documents — some may contain PII (customer name, address).
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated — {len(text)} chars total]"
