# ============================================================
# infra/canary.tf — Lambda Aliases for Canary Deploy
#
# Creates two Lambda aliases on the existing pipeline function:
#
#   staging    — always points to the version just deployed by CI.
#                CI updates this after every successful image push.
#                The latency benchmark and smoke tests run against this alias.
#
#   production — points to the last manually promoted version.
#                Promotion is done via scripts/promote_canary.py or the
#                GitHub Actions "promote" job (requires manual approval).
#
# Canary traffic splitting (optional):
#   When var.canary_version is set, production routes var.canary_weight
#   fraction of traffic to that version. This lets you send 10% of real
#   traffic to the new version before full rollout.
#
#   Example:
#     production_version = "3"   ← 90% of traffic
#     canary_version     = "4"   ← 10% of traffic (new deploy)
#     canary_weight      = 0.1
#
#   After smoke testing, set canary_version = "" to shift 100% to version 4,
#   then set production_version = "4" for the next cycle.
#
# How to use:
#   1. Deploy infra: cd infra && terraform apply
#   2. CI deploys image → publishes new Lambda version → updates staging alias
#   3. Staging smoke tests pass
#   4. Run: python scripts/promote_canary.py --canary 10  (optional 10% canary)
#   5. Monitor CloudWatch dashboard for 15 min
#   6. Run: python scripts/promote_canary.py --promote     (shift 100%)
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

data "aws_lambda_function" "pipeline" {
  function_name = var.lambda_function_name
}

data "aws_caller_identity" "current" {}
data "aws_region"          "current" {}

#          Staging alias                                                                                                                                                                                                                                                     
# Points to $LATEST so CI can update it without publishing a new version.
# All pre-production tests (latency benchmark, smoke test) invoke this alias.

resource "aws_lambda_alias" "staging" {
  name             = "staging"
  description      = "Pre-production — CI deploys here. Run tests before promoting."
  function_name    = data.aws_lambda_function.pipeline.function_name
  function_version = "$LATEST"

  lifecycle {
    # CI updates the underlying $LATEST — Terraform doesn't manage the version pointer
    ignore_changes = [function_version]
  }
}

#          Production alias                                                                                                                                                                                                                                         
# Points to a specific published version (not $LATEST) for stability.
# Optional canary routing: split traffic between current prod and new version.

resource "aws_lambda_alias" "production" {
  name             = "production"
  description      = "Live production traffic. Promoted manually after staging tests pass."
  function_name    = data.aws_lambda_function.pipeline.function_name
  function_version = var.production_version

  # Canary routing: only enabled when canary_version is set
  dynamic "routing_config" {
    for_each = var.canary_version != "" ? [1] : []
    content {
      additional_version_weights = {
        (var.canary_version) = var.canary_weight
      }
    }
  }
}

#          CloudWatch Logs: staging invocations                                                                                                                                                         
# Separate log group for staging so staging noise doesn't pollute production logs.

resource "aws_cloudwatch_log_group" "staging_logs" {
  name              = "/aws/lambda/${var.lambda_function_name}/staging"
  retention_in_days = 7   # staging logs expire quickly — keep costs low
}
