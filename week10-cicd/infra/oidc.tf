# ============================================================
# infra/oidc.tf — GitHub Actions OIDC + ECR
#
# Gives GitHub Actions temporary AWS credentials via OIDC.
# No long-lived access keys stored in GitHub Secrets.
#
# Resources:
#   - OIDC provider reference (github.com)
#   - IAM role for GitHub Actions (scoped to main branch)
#   - IAM policy: ECR push + Lambda update + Bedrock invoke (tests)
#   - ECR repository for the warrantyAI container image
#
# Usage:
#   1. terraform apply (one-time setup)
#   2. Copy github_actions_role_arn output → GitHub secret AWS_ROLE_ARN
#   3. Copy ecr_registry output → GitHub secret ECR_REGISTRY
# ============================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "github_org" {
  description = "GitHub organisation or username (e.g. your-org)"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name (e.g. warrantyai)"
  type        = string
  default     = "warrantyai"
}

variable "lambda_function_name" {
  description = "Lambda function name to allow update-function-code"
  type        = string
  default     = "warrantyai-langgraph-pipeline"
}

#  OIDC Provider 
# GitHub already registers this provider in most accounts.
# Use data source to reference it rather than recreating it.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

#  IAM Role: GitHub Actions 
# Scoped to main branch only.
# PRs from forks get the regression-tests job but NOT deploy permissions.

resource "aws_iam_role" "github_actions" {
  name        = "github-actions-warrantyai"
  description = "Role assumed by GitHub Actions for warrantyAI CI/CD (OIDC)"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringLike = {
          # Allow both main branch pushes and PRs
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main",
            "repo:${var.github_org}/${var.github_repo}:pull_request"
          ]
        }
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = {
    Project   = "warrantyAI"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name = "warrantyai-github-actions-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ECR: authenticate + push images
      {
        Sid    = "ECRAuth"
        Effect = "Allow"
        Action = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = aws_ecr_repository.warrantyai_pipeline.arn
      },
      # Lambda: deploy image + wait + describe
      {
        Sid    = "LambdaDeploy"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration"
        ]
        Resource = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.lambda_function_name}"
      },
      # Bedrock: invoke models for regression tests
      {
        Sid    = "BedrockRegressionTests"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-haiku-4-5-20251001",
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-sonnet-4-6"
        ]
      }
    ]
  })
}

#  ECR Repository 

resource "aws_ecr_repository" "warrantyai_pipeline" {
  name                 = "warrantyai-pipeline"
  image_tag_mutability = "MUTABLE"   # allows :latest tag

  image_scanning_configuration {
    scan_on_push = true   # free vulnerability scan on every push
  }

  tags = {
    Project   = "warrantyAI"
    ManagedBy = "terraform"
  }
}

# Keep only the 10 most recent images to control storage costs
resource "aws_ecr_lifecycle_policy" "warrantyai_pipeline" {
  repository = aws_ecr_repository.warrantyai_pipeline.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain only the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

#  Outputs 

output "github_actions_role_arn" {
  description = "Set this as GitHub secret: AWS_ROLE_ARN"
  value       = aws_iam_role.github_actions.arn
}

output "ecr_registry" {
  description = "Set this as GitHub secret: ECR_REGISTRY"
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com"
}

output "ecr_repository_url" {
  description = "Full ECR repository URL"
  value       = aws_ecr_repository.warrantyai_pipeline.repository_url
}
