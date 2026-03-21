# ============================================================
# infra/cloudwatch_dashboard.tf — Observability Alarms + Dashboard
#
# Alarms:
#   warrantyai-classifier-latency-high
#       Triggers if p95 ClassifierLatency > 8s over a 5-min window.
#       What it catches: Sonnet fallback rate increase, prompt bloat,
#       Bedrock throttling in production.
#
#   warrantyai-token-cost-spike
#       Triggers if avg TokensUsed > 660 tokens/doc over 5 min.
#       (660 = 550 baseline × 1.20)
#       What it catches: accidental prompt length increase, unexpected
#       Sonnet fallback accumulation.
#
#   warrantyai-model-fallback-rate-high
#       Triggers if SUM(ModelFallback) > 30% of total calls in 5 min.
#       What it catches: a prompt change that causes Haiku to consistently
#       underperform and fall back to the more expensive Sonnet.
#
# Dashboard: warrantyai-observability
#   Four widgets side by side:
#   [Classifier Latency p95] [Token Usage] [Model Fallback Rate] [Risk Level Distribution]
# ============================================================

locals {
  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
}

#     Alarm: Classifier latency                                                                          

resource "aws_cloudwatch_metric_alarm" "latency_high" {
  alarm_name          = "warrantyai-classifier-latency-high"
  alarm_description   = "Classifier p95 latency exceeded ${var.latency_alarm_threshold_ms}ms — check Sonnet fallback rate and Bedrock throttling."
  namespace           = "WarrantyAI/Agent"
  metric_name         = "ClassifierLatency"
  statistic           = "p95"
  period              = 300   # 5-minute window
  evaluation_periods  = 1
  threshold           = var.latency_alarm_threshold_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    AgentName = "classifier"
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

#     Alarm: Token cost spike                                                                             

resource "aws_cloudwatch_metric_alarm" "token_spike" {
  alarm_name          = "warrantyai-token-cost-spike"
  alarm_description   = "Avg tokens/doc exceeded ${var.token_spike_threshold} — possible prompt bloat or unexpected Sonnet fallback accumulation."
  namespace           = "WarrantyAI/Agent"
  metric_name         = "TokensUsed"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.token_spike_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    AgentName = "classifier"
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

#     Alarm: Model fallback rate                                                                         
# Uses a metric math expression: SUM(fallbacks) / SUM(all_calls) > 0.30

resource "aws_cloudwatch_metric_alarm" "fallback_rate_high" {
  alarm_name          = "warrantyai-model-fallback-rate-high"
  alarm_description   = "Haiku→Sonnet fallback rate exceeded 30% — Haiku may no longer meet confidence threshold reliably."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0.30
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "fallbacks"
    return_data = false
    metric {
      namespace   = "WarrantyAI/Agent"
      metric_name = "ModelFallback"
      stat        = "Sum"
      period      = 300
      dimensions  = { AgentName = "classifier" }
    }
  }

  metric_query {
    id          = "total_calls"
    return_data = false
    metric {
      namespace   = "WarrantyAI/Agent"
      metric_name = "TokensUsed"
      stat        = "SampleCount"
      period      = 300
      dimensions  = { AgentName = "classifier" }
    }
  }

  metric_query {
    id          = "fallback_rate"
    expression  = "fallbacks / total_calls"
    label       = "Fallback Rate"
    return_data = true
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

#     CloudWatch Dashboard                                                                                  

resource "aws_cloudwatch_dashboard" "warrantyai_observability" {
  dashboard_name = "warrantyai-observability"

  dashboard_body = jsonencode({
    widgets = [

      # Row 1, Col 1: Classifier Latency
      {
        type   = "metric"
        x = 0
        y = 0
        width = 6
        height = 6
        properties = {
          title  = "Classifier Latency"
          view   = "timeSeries"
          stat   = "p95"
          period = 300
          metrics = [
            ["WarrantyAI/Agent", "ClassifierLatency", "AgentName", "classifier", { label = "p95 latency (ms)", color = "#1f77b4" }],
            ["...", { stat = "p50", label = "p50 latency (ms)", color = "#aec7e8" }]
          ]
          annotations = {
            horizontal = [
              { value = var.latency_alarm_threshold_ms, label = "SLO threshold (8s)", color = "#d62728" }
            ]
          }
          yAxis = { left = { min = 0, label = "Milliseconds" } }
        }
      },

      # Row 1, Col 2: Token Usage per Document
      {
        type   = "metric"
        x = 6
        y = 0
        width = 6
        height = 6
        properties = {
          title  = "Token Usage per Document"
          view   = "timeSeries"
          stat   = "Average"
          period = 300
          metrics = [
            ["WarrantyAI/Agent", "TokensUsed", "AgentName", "classifier", { label = "avg tokens/doc", color = "#2ca02c" }]
          ]
          annotations = {
            horizontal = [
              { value = var.token_spike_threshold, label = "Spike threshold (660)", color = "#d62728" }
            ]
          }
          yAxis = { left = { min = 0, label = "Tokens" } }
        }
      },

      # Row 1, Col 3: Model Fallback Rate
      {
        type   = "metric"
        x = 12
        y = 0 
        width = 6
        height = 6
        properties = {
          title  = "Model Fallback Rate (Haiku → Sonnet)"
          view   = "timeSeries"
          period = 300
          metrics = [
            [{ id = "f", expression = "fallbacks / total_calls", label = "Fallback rate", color = "#ff7f0e" }],
            ["WarrantyAI/Agent", "ModelFallback", "AgentName", "classifier", { id = "fallbacks", visible = false, stat = "Sum" }],
            ["WarrantyAI/Agent", "TokensUsed",    "AgentName", "classifier", { id = "total_calls", visible = false, stat = "SampleCount" }]
          ]
          annotations = {
            horizontal = [{ value = 0.3, label = "Alarm threshold (30%)", color = "#d62728" }]
          }
          yAxis = { left = { min = 0, max = 1, label = "Rate (0–1)" } }
        }
      },

      # Row 1, Col 4: Risk Level Distribution
      {
        type   = "metric"
        x = 18
        y = 0
        width = 6
        height = 6
        properties = {
          title  = "Risk Level Distribution"
          view   = "timeSeries"
          stat   = "Sum"
          period = 300
          metrics = [
            ["WarrantyAI/Agent", "RiskLevelHigh",   "AgentName", "classifier", { label = "HIGH",   color = "#d62728" }],
            ["WarrantyAI/Agent", "RiskLevelMedium", "AgentName", "classifier", { label = "MEDIUM", color = "#ff7f0e" }],
            ["WarrantyAI/Agent", "RiskLevelLow",    "AgentName", "classifier", { label = "LOW",    color = "#2ca02c" }]
          ]
          yAxis = { left = { min = 0, label = "Documents processed" } }
        }
      },

      # Row 2: Alarm Status
      {
        type   = "alarm"
        x = 0
        y = 6
        width = 24
        height = 2
        properties = {
          title  = "Active Alarms"
          alarms = [
            aws_cloudwatch_metric_alarm.latency_high.arn,
            aws_cloudwatch_metric_alarm.token_spike.arn,
            aws_cloudwatch_metric_alarm.fallback_rate_high.arn,
          ]
        }
      }
    ]
  })
}
