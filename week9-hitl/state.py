"""
warrantyAI — Week 9
WarrantyState: updated with HITL fields

New fields added this week:
  hitl_status    — tracks whether human review was triggered and what happened
  reviewed_by    — email of reviewer (extracted from approve/reject link click)
  reviewed_at    — ISO 8601 timestamp of review decision
  hitl_token     — short token embedded in approve/reject URLs (= document_id for Week 9)
"""

from typing import TypedDict, Optional


class WarrantyState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────
    document_id: str
    s3_key: str
    tenant_id: str

    # ── Reader Agent output ──────────────────────────────────────────────
    raw_text: Optional[str]
    structured_data: Optional[dict]

    # ── Classifier Agent output ──────────────────────────────────────────
    category: Optional[str]
    expiry_date: Optional[str]
    risk_level: Optional[str]
    model_used: Optional[str]
    guardrail_triggered: Optional[bool]

    # ── HITL Agent output (NEW Week 9) ───────────────────────────────────
    hitl_required: Optional[bool]       # True if risk_level == "high"
    hitl_status: Optional[str]          # "pending_review" | "approved" | "rejected" | "skipped"
    hitl_token: Optional[str]           # document_id used in approve/reject URL
    reviewed_by: Optional[str]          # email from reviewer link click
    reviewed_at: Optional[str]          # ISO 8601 timestamp

    # ── Reminder Agent output ────────────────────────────────────────────
    notification_sent: Optional[bool]
    notification_message: Optional[str]
    sns_message_id: Optional[str]

    # ── Audit + Error tracking ───────────────────────────────────────────
    audit_log: list
    errors: list
