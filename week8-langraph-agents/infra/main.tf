# warrantyAI — Week 8
# infra/main.tf — LangGraph Pipeline Lambda + IAM + S3 trigger
#
# Deploy order:
#   1. Build Lambda package:  make build
#   2. Deploy infra:          cd infra && terraform init && terraform apply
#
# Depends on: Week 1-7 S3 buckets, Week 7 guardrail + audit bucket

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = var.aws_region
  lambda_name = "warrantyai-langgraph-pipeline"
}

# Reference existing Week 1-7 resources via data sources

data "aws_s3_bucket" "warranty_docs" {
  bucket = var.warranty_docs_bucket_name
}

data "aws_s3_bucket" "audit_logs" {
  bucket = var.audit_logs_bucket_name
}

# Lambda deployment package
# Built by: make build  (see Makefile)
# Zip includes: state.py, graph.py, run.py, agents/
# Dependencies (langgraph, boto3) are in the Lambda layer (deps.zip)

data "archive_file" "pipeline_code" {
  type        = "zip"
  output_path = "${path.module}/pipeline_code.zip"

  source {
    content  = file("${path.module}/../state.py")
    filename = "state.py"
  }
  source {
    content  = file("${path.module}/../graph.py")
    filename = "graph.py"
  }
  source {
    content  = file("${path.module}/../run.py")
    filename = "run.py"
  }
  source {
    content  = file("${path.module}/../agents/__init__.py")
    filename = "agents/__init__.py"
  }
  source {
    content  = file("${path.module}/../agents/reader.py")
    filename = "agents/reader.py"
  }
  source {
    content  = file("${path.module}/../agents/classifier.py")
    filename = "agents/classifier.py"
  }
  source {
    content  = file("${path.module}/../agents/reminder.py")
    filename = "agents/reminder.py"
  }
}

# Lambda layer for Python dependencies
# Build with: make build-layer
# Creates deps.zip with langgraph + langchain-core installed for linux/arm64

resource "aws_lambda_layer_version" "deps" {
  layer_name          = "warrantyai-langgraph-deps"
  filename            = "${path.module}/deps.zip"
  source_code_hash    = fileexists("${path.module}/deps.zip") ? filebase64sha256("${path.module}/deps.zip") : ""
  compatible_runtimes = ["python3.12"]
  compatible_architectures = ["arm64"]

  lifecycle {
    create_before_destroy = true
  }
}

# IAM: Pipeline Lambda execution role
# Single role combining Reader + Classifier + Reminder permissions.
# All 3 agents run in one Lambda process (LangGraph StateGraph.invoke).

resource "aws_iam_role" "pipeline" {
  name = "warrantyai-pipeline-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = {
    Project = "warrantyAI"
    Week    = "8"
  }
}

resource "aws_iam_role_policy" "pipeline" {
  name = "warrantyai-pipeline-lambda-policy"
  role = aws_iam_role.pipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Reader: Textract
      {
        Sid    = "Textract"
        Effect = "Allow"
        Action = [
          "textract:DetectDocumentText",
          "textract:AnalyzeDocument",
          "textract:StartDocumentTextDetection",
          "textract:GetDocumentTextDetection"
        ]
        Resource = "*"
      },
      # Reader: S3 warranty docs read
      {
        Sid    = "S3WarrantyDocsRead"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          data.aws_s3_bucket.warranty_docs.arn,
          "${data.aws_s3_bucket.warranty_docs.arn}/*"
        ]
      },
      # Classifier + Reminder: Bedrock Haiku + Sonnet + Guardrail
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${local.region}::foundation-model/anthropic.claude-haiku-4-5-20251001",
          "arn:aws:bedrock:${local.region}::foundation-model/anthropic.claude-sonnet-4-6"
        ]
      },
      {
        Sid    = "BedrockGuardrail"
        Effect = "Allow"
        Action = ["bedrock:ApplyGuardrail"]
        Resource = var.governanceshield_guardrail_id != "" ? [
          "arn:aws:bedrock:${local.region}:${local.account_id}:guardrail/${var.governanceshield_guardrail_id}"
        ] : ["arn:aws:bedrock:${local.region}:${local.account_id}:guardrail/*"]
      },
      # All agents: S3 audit log writes
      {
        Sid    = "AuditLogWrite"
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "${data.aws_s3_bucket.audit_logs.arn}/reader/*",
          "${data.aws_s3_bucket.audit_logs.arn}/classifier/*",
          "${data.aws_s3_bucket.audit_logs.arn}/reminder/*"
        ]
      },
      # Reminder: SNS publish
      {
        Sid    = "SNSPublish"
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = aws_sns_topic.warranty_notifications.arn
      },
      # CloudWatch Logs
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.lambda_name}:*"
      }
    ]
  })
}

# Lambda function

resource "aws_lambda_function" "pipeline" {
  function_name    = local.lambda_name
  role             = aws_iam_role.pipeline.arn
  handler          = "run.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]  # Graviton — 20% cheaper (Week 6 FinOps)
  memory_size      = var.lambda_memory_mb
  timeout          = var.lambda_timeout_seconds

  filename         = data.archive_file.pipeline_code.output_path
  source_code_hash = data.archive_file.pipeline_code.output_base64sha256

  layers = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      GOVERNANCESHIELD_ID      = var.governanceshield_guardrail_id
      GOVERNANCESHIELD_VERSION = var.governanceshield_guardrail_version
      WARRANTY_SNS_TOPIC_ARN   = aws_sns_topic.warranty_notifications.arn
      AUDIT_BUCKET             = var.audit_logs_bucket_name
    }
  }

  tags = {
    Project = "warrantyAI"
    Week    = "8"
    Agent   = "langgraph-pipeline"
  }
}

# CloudWatch Log Group

resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 14

  tags = {
    Project = "warrantyAI"
    Week    = "8"
  }
}

# S3 trigger: new warranty PDF → run pipeline

resource "aws_lambda_permission" "s3_trigger" {
  statement_id  = "AllowS3InvokePipeline"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pipeline.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = data.aws_s3_bucket.warranty_docs.arn
}

resource "aws_s3_bucket_notification" "warranty_docs_trigger" {
  bucket = data.aws_s3_bucket.warranty_docs.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "tenants/"
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.s3_trigger]
}

#  CloudWatch alarm: pipeline errors

resource "aws_cloudwatch_metric_alarm" "pipeline_errors" {
  alarm_name          = "warrantyai-pipeline-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "warrantyAI LangGraph pipeline Lambda errors > 5 in 5 min"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.pipeline.function_name
  }

  alarm_actions = [aws_sns_topic.warranty_notifications.arn]
}

esource "aws_sns_topic" "warranty_notifications" {
  name = "warrantyai-notifications"

  tags = {
    Project = "warrantyAI"
    Week    = "8"
    Purpose = "Warranty expiry alerts from Reminder agent"
  }
}

# Email subscription (for testing — replace with real endpoint)
resource "aws_sns_topic_subscription" "warranty_email" {
  topic_arn = aws_sns_topic.warranty_notifications.arn
  protocol  = "email"
  endpoint  = var.notification_email  # Set in terraform.tfvars
}