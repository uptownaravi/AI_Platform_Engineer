# ============================================================
# infra/outputs.tf — Week 11 Observability
# ============================================================

output "staging_alias_arn" {
  description = "ARN of the staging Lambda alias — invoke this in smoke tests"
  value       = aws_lambda_alias.staging.arn
}

output "production_alias_arn" {
  description = "ARN of the production Lambda alias"
  value       = aws_lambda_alias.production.arn
}

output "staging_invoke_url" {
  description = "AWS CLI command to invoke the staging alias"
  value       = "aws lambda invoke --function-name ${var.lambda_function_name}:staging --payload '{}' response.json"
}

output "cloudwatch_dashboard_url" {
  description = "Direct link to the warrantyAI observability dashboard"
  value       = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=warrantyai-observability"
}

output "latency_alarm_arn" {
  description = "ARN of the classifier latency alarm"
  value       = aws_cloudwatch_metric_alarm.latency_high.arn
}

output "token_spike_alarm_arn" {
  description = "ARN of the token cost spike alarm"
  value       = aws_cloudwatch_metric_alarm.token_spike.arn
}
