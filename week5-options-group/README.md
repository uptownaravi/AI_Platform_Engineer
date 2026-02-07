# Week 5: Agentic Advocate & Semantic Routing

From passive data pipeline to intelligent decision-maker. This week introduces a **Semantic Router** that decides whether a user needs *Knowledge* (RAG lookup) or *Action* (custom calculation).

## Architecture Overview

A **Decoupled Intelligence Factory** where each AWS service owns one phase:

| Component | Role |
|-----------|------|
| **S3** | Landing zone for PDFs and refined Markdown sidecars |
| **SQS** | Async buffer for long-running Lambda tasks |
| **Lambda** | Core orchestrator (Ingestion Engine + Agent Action Group) |
| **Textract** | Async multi-page OCR (the 5-page LG warranty) |
| **SageMaker** | NuMarkdown-8B-Thinking for complex table reasoning |
| **Bedrock Knowledge Base** | RAG store for semantic warranty clause access |
| **Bedrock Agent** | The Semantic Router (routes to KB or Lambda Action) |
| **DynamoDB** | Sub-second lookups for Brand, Model, Expiry facts |
| **CloudWatch** | FinOps Dashboard (token burn, operational costs) |

## How It Works

### Event Parsing (The Router)
- **Ingestion Mode**: SQS trigger (`Records` in event) → Process PDFs
- **Action Mode**: Bedrock Agent trigger → Apply business logic

### Visual Processing (The Eyes)
Async Textract handles multi-page documents. Sync calls fail on 5+ page PDFs.

### Layout Reasoning (The Brain)
NuMarkdown refines messy OCR into structured Markdown. Critical for complex tables (e.g., LG's 1-year product vs. 10-year compressor warranty).

### Semantic Action (The Advocate)
Two decision branches:
1. **Beyond Municipal Limits** → Clause 5 applies: "on-site warranty not applicable"
2. **Service Charges** → Always payable by customer (Page 4), even if parts are free

## Files

- **options-group.py**: Lambda handler for ingestion + action execution
- **week5-infra.tf**: Terraform resources (SQS, Lambda, Bedrock Agent, Knowledge Base)
