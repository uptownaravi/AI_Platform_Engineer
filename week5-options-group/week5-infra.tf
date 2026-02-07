# --- 1. SQS Buffer & Trigger ---
resource "aws_sqs_queue" "ingestion_queue" {
  name                       = "WarrantyAI-IngestionQueue"
  visibility_timeout_seconds = 300
}

# --- 2. Lambda Orchestrator & Action Group ---
resource "aws_lambda_function" "agent_orchestrator" {
  function_name = "WarrantyAI-AgentOrchestrator"
  role          = aws_iam_role.lambda_role.arn
  handler       = "options-group.lambda_handler"
  runtime       = "python3.12"
  timeout       = 300

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.records.name
      KB_ID      = aws_bedrockagent_knowledge_base.warranty_kb.id
    }
  }
}

# --- 3. Bedrock Agent (The Semantic Router) ---
resource "aws_bedrockagent_agent" "warranty_advocate" {
  agent_name                  = "WarrantyAdvocate"
  agent_resource_role_arn     = aws_iam_role.agent_role.arn
  foundation_model            = "mistral.mistral-7b-instruct-v0:2"
  instruction                 = "You are a Warranty Advocate. Use the Knowledge Base for policy questions. Use the Action Group for fee calculations."

  action_group {
    action_group_name          = "EligibilityTools"
    action_group_executor {
      lambda = aws_lambda_function.agent_orchestrator.arn
    }
    api_schema {
      payload = file("api_schema.json") # Defines the /check-fees endpoint
    }
  }
}