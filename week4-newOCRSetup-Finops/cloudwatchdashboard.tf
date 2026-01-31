resource "aws_cloudwatch_dashboard" "warranty_ai_finops" {
  dashboard_name = "WarrantyAI-FinOps-Native"

  dashboard_body = jsonencode({
    widgets = [
      # Widget 1: Bedrock Token Usage (Native Metrics)
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            [ "AWS/Bedrock", "InputTokenCount", "ModelId", "mistral.mistral-7b-instruct-v0:2" ],
            [ ".", "OutputTokenCount", ".", "." ]
          ]
          view    = "timeSeries"
          region  = "ap-south-1"
          title   = "Bedrock Native Token Consumption"
        }
      },

      # Widget 2: Bedrock Real-Time Cost (Metric Math)
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            # m1 = Input Tokens, m2 = Output Tokens (Not visible, used for calculation)
            [ "AWS/Bedrock", "InputTokenCount", "ModelId", "mistral.mistral-7b-instruct-v0:2", { "id": "m1", "visible": false } ],
            [ ".", "OutputTokenCount", ".", ".", { "id": "m2", "visible": false } ],
            # Cost Formula: (InputTokens/1000 * $0.00015) + (OutputTokens/1000 * $0.0002)
            [ { "expression": "((m1/1000)*0.00015) + ((m2/1000)*0.0002)", "label": "Estimated USD Cost", "id": "e1" } ]
          ]
          view    = "timeSeries"
          region  = "ap-south-1"
          title   = "Bedrock Dynamic Cost Tracker"
        }
      },

      # Widget 3: SageMaker (NuMarkdown) Performance
      {
        type   = "metric"
        width  = 24
        height = 6
        properties = {
          metrics = [
            [ "AWS/SageMaker", "Invocations", "EndpointName", "NuMarkdown-Endpoint", "VariantName", "AllVariants" ],
            [ ".", "ModelLatency", ".", ".", ".", ".", { "stat": "Average" } ],
            [ ".", "OverheadLatency", ".", ".", ".", ".", { "stat": "Average" } ]
          ]
          view    = "timeSeries"
          region  = "ap-south-1"
          title   = "NuMarkdown (SageMaker) Throughput & Latency"
        }
      }
    ]
  })
}