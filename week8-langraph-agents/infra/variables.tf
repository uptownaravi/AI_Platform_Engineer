variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-south-1"
}

variable "warranty_docs_bucket_name" {
  description = "S3 bucket name for warranty PDF documents (created in Week 1)"
  type        = string
}

variable "audit_logs_bucket_name" {
  description = "S3 bucket name for audit logs (created in Week 7)"
  type        = string
  default     = "warrantyai-audit-logs"
}

variable "notification_email" {
  description = "Email address to receive warranty expiry notifications via SNS"
  type        = string
}

variable "governanceshield_guardrail_id" {
  description = "Bedrock Guardrail ID for GovernanceShield-Week7 (from Week 7 Terraform output)"
  type        = string
  default     = ""
}

variable "governanceshield_guardrail_version" {
  description = "Bedrock Guardrail version (from Week 7 Terraform output)"
  type        = string
  default     = "DRAFT"
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB — 256 is minimum viable for LangGraph (Week 6 FinOps)"
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout — 300s covers Textract async polling"
  type        = number
  default     = 300
}
