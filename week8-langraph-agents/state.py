"""
warrantyAI — Week 8
WarrantyState: shared state schema across all LangGraph agents

Every agent reads from this, writes a partial update back to this.
Nothing is passed directly between agents — state is the only contract.
"""

from typing import TypedDict, Optional


class WarrantyState(TypedDict):
    #   Input                               
    document_id: str          # Unique ID for this warranty document
    s3_key: str               # S3 object key e.g. "tenants/t001/doc123.pdf"
    tenant_id: str            # Multi-tenant isolation key

    #   Reader Agent output                        
    raw_text: Optional[str]           # Full text extracted by Textract
    structured_data: Optional[dict]   # Parsed fields: product, brand, dates, etc.

    #   Classifier Agent output                      
    category: Optional[str]       # "appliance" | "electronics" | "commercial" | "other"
    expiry_date: Optional[str]    # ISO 8601 e.g. "2027-03-15"
    risk_level: Optional[str]     # "low" | "medium" | "high"
    model_used: Optional[str]     # "haiku" | "sonnet" (sonnet = haiku fallback)
    guardrail_triggered: Optional[bool]  # True if GovernanceShield blocked anything

    #   Reminder Agent output                       
    notification_sent: Optional[bool]
    notification_message: Optional[str]
    sns_message_id: Optional[str]   # Returned by SNS on successful publish

    #   Audit + Error tracking                      ─
    audit_log: list            # Each agent appends its own audit entry
    errors: list               # Non-fatal errors — pipeline continues
