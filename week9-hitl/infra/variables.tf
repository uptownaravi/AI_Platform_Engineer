# warrantyAI — Week 9
# infra/variables.tf

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-south-1"
}

variable "warranty_docs_bucket_name" {
  description = "S3 bucket name for warranty PDF uploads"
  type        = string
  default     = "warrantyai-documents"
}

variable "audit_logs_bucket_name" {
  description = "S3 bucket name for audit logs"
  type        = string
  default     = "warrantyai-audit-logs"
}

variable "notification_email" {
  description = "Email address for tenant warranty expiry notifications"
  type        = string
}

variable "reviewer_email" {
  description = "Email address for HITL review notifications (high-risk warranty approvals)"
  type        = string
}

variable "governanceshield_guardrail_id" {
  description = "Bedrock Guardrail ID for GovernanceShield (Week 7 output)"
  type        = string
  default     = ""
}

variable "governanceshield_guardrail_version" {
  description = "Bedrock Guardrail version to pin in production"
  type        = string
  default     = "DRAFT"
}

variable "lambda_memory_mb" {
  description = "Lambda memory allocation in MB (FinOps: minimum viable)"
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds (covers Textract async polling)"
  type        = number
  default     = 300
}

# ── Week 9: HITL additions ────────────────────────────────────────────────

variable "resume_lambda_arn" {
  description = "ARN of the resume.py Lambda function (warrantyai-resume)"
  type        = string
}

variable "pipeline_lambda_arn" {
  description = "ARN of the main pipeline Lambda (warrantyai-langgraph-pipeline)"
  type        = string
}
