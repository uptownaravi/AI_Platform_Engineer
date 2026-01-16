# 1. IAM Role for Bedrock to access S3 and OpenSearch
resource "aws_iam_role" "bedrock_kb_role" {
  name = "WarrantyAI-KB-Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
    }]
  })
}

# 2. OpenSearch Serverless Collection (The Vector Database)
resource "aws_opensearchserverless_collection" "warranty_vectors" {
  name = "warranty-vectors"
  type = "VECTORSEARCH"
}

# 3. The Bedrock Knowledge Base
resource "aws_bedrockagent_knowledge_base" "warranty_kb" {
  name     = "WarrantyAI-KB"
  role_arn = aws_iam_role.bedrock_kb_role.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:ap-south-1::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.warranty_vectors.arn
      vector_index_name = "bedrock-knowledge-base-default-index"
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }
}

# 4. Connect your existing S3 Bucket as the Data Source
resource "aws_bedrockagent_data_source" "warranty_ds" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.warranty_kb.id
  name              = "WarrantyAI-S3-Source"
  
  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = "arn:aws:s3:::warrantyai"
    }
  }
}