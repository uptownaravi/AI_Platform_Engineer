# ============================================================
# infra/variables.tf — Week 11 Observability
# ============================================================

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "lambda_function_name" {
  description = "Name of the existing warrantyAI pipeline Lambda function"
  type        = string
  default     = "warrantyai-langgraph-pipeline"
}

variable "production_version" {
  description = <<EOT
Lambda version number for the production alias.
Set this to the published version number when promoting (e.g. "3").
Use "1" for initial setup — you must publish at least one version first:
  aws lambda publish-version --function-name warrantyai-langgraph-pipeline
EOT
  type        = string
  default     = "1"
}

variable "canary_version" {
  description = <<EOT
Lambda version to route canary traffic to during staged rollout.
Set to "" (empty) to disable canary routing — all traffic goes to production_version.
Set to a version number (e.g. "4") to route canary_weight % to that version.
EOT
  type        = string
  default     = ""
}

variable "canary_weight" {
  description = "Fraction of production traffic routed to canary_version (0.0–1.0). Only used when canary_version is set."
  type        = number
  default     = 0.1
}

variable "latency_alarm_threshold_ms" {
  description = "CloudWatch alarm threshold: classifier p95 latency above this triggers a notification"
  type        = number
  default     = 8000
}

variable "token_spike_threshold" {
  description = "CloudWatch alarm threshold: avg tokens/doc above this triggers a notification (20% above baseline of 550)"
  type        = number
  default     = 660
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN to receive CloudWatch alarm notifications. Leave empty to skip alarm actions."
  type        = string
  default     = ""
}
