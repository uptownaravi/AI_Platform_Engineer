terraform {
  backend "s3" {
    bucket = "<backend-state-bucket-name>"
    key    = "terraform/state"
    region = "us-east-1"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.28"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
}

# --- 0. DATA SOURCE FOR ACCOUNT ID ---
data "aws_caller_identity" "current" {}

# --- 1. ZIP THE PYTHON CODE ---
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/ocr.py"
  output_path = "${path.module}/ocr.zip"
}

# --- 2. SQS QUEUE (The Buffer) ---
resource "aws_sqs_queue" "ingestion_queue" {
  name                       = "WarrantyAI-IngestionQueue"
  visibility_timeout_seconds = 300
}

resource "aws_sqs_queue_policy" "ingestion_queue_policy" {
  queue_url = aws_sqs_queue.ingestion_queue.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.ingestion_queue.arn
        Condition = {
          ArnLike = {
            "aws:SourceArn" = aws_s3_bucket.warranty_documents.arn
          }
        }
      }
    ]
  })
}

# --- 3. S3 BUCKET FOR DOCUMENTS ---
resource "aws_s3_bucket" "warranty_documents" {
  bucket = "<replace-with-required-bucket-name>"
}

# --- 4. S3 NOTIFICATION (The Trigger) ---
resource "aws_s3_bucket_notification" "trigger" {
  bucket = aws_s3_bucket.warranty_documents.bucket
  queue {
    queue_arn     = aws_sqs_queue.ingestion_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_suffix = ".pdf"
  }
}

# --- 5. DYNAMODB (The Facts Store) ---
resource "aws_dynamodb_table" "records" {
  name           = "WarrantyAI-Metadata"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "user_id"
  range_key      = "doc_id"
  
  attribute {
    name = "user_id"
    type = "S"
  }
  
  attribute {
    name = "doc_id"
    type = "S"
  }
}

# --- 6. LAMBDA FUNCTION (The Orchestrator) ---
resource "aws_lambda_function" "pre_processor" {
  function_name = "WarrantyAI-PreProcessor"
  role          = aws_iam_role.lambda_role.arn
  handler       = "ocr.lambda_handler"
  runtime       = "python3.12"
  timeout       = 300
  
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.records.name
      # FIX: Referencing the resources directly instead of variables
      KB_ID      = aws_bedrockagent_knowledge_base.warranty_kb.id
      # Removed DS_ID as data source is no longer used with S3_VECTORS
    }
  }
}

# --- 7. SQS TO LAMBDA TRIGGER ---
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.ingestion_queue.arn
  function_name    = aws_lambda_function.pre_processor.arn
  batch_size       = 1
}

# --- 8. IAM ROLE & POLICIES ---
resource "aws_iam_role" "lambda_role" {
  name = "WarrantyAI-Lambda-Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name = "WarrantyAI-Lambda-Permissions"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Effect = "Allow"
        Resource = aws_sqs_queue.ingestion_queue.arn
      },
      {
        Action = ["dynamodb:PutItem", "dynamodb:GetItem"]
        Effect = "Allow"
        Resource = aws_dynamodb_table.records.arn
      },
      {
        Action = ["textract:*", "bedrock:*", "s3:GetObject", "s3:PutObject"]
        Effect = "Allow"
        Resource = "*"
      },
      {
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Effect = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# --- 9. BEDROCK KNOWLEDGE BASE ---

resource "aws_iam_role" "bedrock_kb_role" {
  name = "WarrantyAI-BedrockKB-Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "bedrock_kb_permissions" {
  name = "WarrantyAI-BedrockKB-Permissions"
  role = aws_iam_role.bedrock_kb_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = ["s3vectors:CreateIndex", "s3vectors:PutVectors", "s3vectors:QueryVectors", "s3vectors:DeleteVectors", "s3vectors:GetVectors" ]
        Effect = "Allow"
        Resource = "*"
      }
    ]
  })
}

# New S3 Vectors resources
resource "aws_s3vectors_vector_bucket" "warranty_vector_bucket" {
  vector_bucket_name = "warrantyai-vectors-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3vectors_index" "warranty_index" {
  index_name         = "warrantyai-index"
  vector_bucket_name = aws_s3vectors_vector_bucket.warranty_vector_bucket.vector_bucket_name

  data_type       = "float32"
  dimension       = 256
  distance_metric = "euclidean"
}

resource "aws_bedrockagent_knowledge_base" "warranty_kb" {
  name     = "WarrantyAI-KB"
  role_arn = aws_iam_role.bedrock_kb_role.arn

  knowledge_base_configuration {
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:ap-south-1::foundation-model/amazon.titan-embed-text-v2:0"
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = 256
          embedding_data_type = "FLOAT32"
        }
      }
    }
    type = "VECTOR"
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.warranty_index.index_arn
    }
  }
}