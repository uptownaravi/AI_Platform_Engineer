# warrantyAI — Week 9
# infra/dynamodb.tf — HITL queue table + API Gateway approve/reject routes

# ── DynamoDB: warrantyai-hitl-queue ──────────────────────────────────────

resource "aws_dynamodb_table" "hitl_queue" {
  name         = "warrantyai-hitl-queue"
  billing_mode = "PAY_PER_REQUEST"   # on-demand — FinOps Week 6 principle
  hash_key     = "document_id"
  range_key    = "sk"

  attribute {
    name = "document_id"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # TTL: auto-expire unactioned reviews after 7 days
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # GSI: query all pending reviews (for an admin dashboard later)
  global_secondary_index {
    name            = "status-index"
    hash_key        = "sk"
    range_key       = "document_id"
    projection_type = "ALL"
  }

  tags = {
    Project = "warrantyAI"
    Week    = "9"
    Purpose = "HITL review queue for high-risk warranties"
  }
}

output "hitl_table_name" {
  value       = aws_dynamodb_table.hitl_queue.name
  description = "Set as HITL_TABLE_NAME env var in Lambda"
}

# ── API Gateway: approve/reject routes ───────────────────────────────────

resource "aws_apigatewayv2_api" "hitl_api" {
  name          = "warrantyai-hitl-api"
  protocol_type = "HTTP"

  tags = {
    Project = "warrantyAI"
    Week    = "9"
  }
}

resource "aws_apigatewayv2_stage" "hitl_stage" {
  api_id      = aws_apigatewayv2_api.hitl_api.id
  name        = "prod"
  auto_deploy = true
}

# Lambda integration — points to resume.py Lambda
resource "aws_apigatewayv2_integration" "resume_lambda" {
  api_id                 = aws_apigatewayv2_api.hitl_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.resume_lambda_arn
  payload_format_version = "2.0"
}

# Route: GET /approve/{document_id}
resource "aws_apigatewayv2_route" "approve" {
  api_id    = aws_apigatewayv2_api.hitl_api.id
  route_key = "GET /approve/{document_id}"
  target    = "integrations/${aws_apigatewayv2_integration.resume_lambda.id}"
}

# Route: GET /reject/{document_id}
resource "aws_apigatewayv2_route" "reject" {
  api_id    = aws_apigatewayv2_api.hitl_api.id
  route_key = "GET /reject/{document_id}"
  target    = "integrations/${aws_apigatewayv2_integration.resume_lambda.id}"
}

# Allow API Gateway to invoke the resume Lambda
resource "aws_lambda_permission" "hitl_api_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.resume_lambda_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.hitl_api.execution_arn}/*/*"
}

output "hitl_api_base_url" {
  value       = aws_apigatewayv2_stage.hitl_stage.invoke_url
  description = "Set as HITL_API_BASE_URL env var — used to build approve/reject links"
}
