
# Week 3: OCR + Vector Knowledge Base (S3 Vectors)
### Overview
Week 3 combines Optical Character Recognition (OCR) with AI-powered document understanding and a serverless vector knowledge base. Instead of clean PDFs, we now handle real-world messy documents (blurry images, screenshots, scanned receipts) using Amazon Textract. The extracted text is semantically structured with an LLM, then automatically indexed into a Bedrock Knowledge Base backed by S3 Vectors — a new, cost-effective vector storage layer.

### Key Evolution from Week 2:

Week 2: Assumed clean PDFs → direct embedding
Week 3: Handle any document format → OCR → LLM structuring → S3 Vectors indexing

Technical Architecture
┌─────────────────────┐
│  S3 Upload          │
│  (Images/PDFs)      │
└──────────┬──────────┘
           │ S3 Event → SQS
           ▼
┌─────────────────────┐
│  Lambda Processor   │
│  (Orchestrator)     │
└──────────┬──────────┘
           │
     ┌─────┴─────┬──────────┐
     ▼           ▼          ▼
  Textract    Bedrock    DynamoDB
  (OCR)       (LLM)      (Metadata)
     │           │          │
     └─────┬─────┴──────────┘
           ▼
     ┌──────────────┐
     │  S3 Vectors  │
     │  (Vector DB) │
     └──────────────┘
           │
           ▼
     ┌──────────────────────┐
     │ Bedrock Knowledge    │
     │ Base (Queryable RAG) │
     └──────────────────────┘

### How It Works (3-Layer Processing)
Layer 1: Visual Extraction (Textract)
Accepts S3 object (PDF or image)
Uses Amazon Textract's analyze_document() API
Extracts text from all lines and blocks
Handles unsupported formats gracefully
Output: Raw text string (may contain OCR noise)

Layer 2: Intelligence Structuring (LLM)
Sends raw OCR text to Mistral 7B on Bedrock
Prompt: "Extract Brand, Model, Purchase Date, Expiry Date as JSON"
LLM cleans noise and returns structured JSON
Temperature = 0.1 (deterministic, not creative)

Layer 3: Isolation & Indexing (S3 Vectors)
Security Model: Multi-tenancy via user_id metadata attribute. Queries are pre-filtered at the vector DB level.

### Project Structure
main.tf — Infrastructure Components
Key Resources:

SQS Queue (WarrantyAI-IngestionQueue): 300s visibility timeout
S3 Bucket (warranty_documents): Document storage
S3 → SQS Notification: Triggers on .pdf uploads
Lambda Function (WarrantyAI-PreProcessor): Processes documents
DynamoDB Table (WarrantyAI-Metadata): Stores facts (Hash: user_id, Range: doc_id)
S3 Vectors Resources:
Vector bucket (stores embeddings)
Vector index (256-dim Euclidean)
Bedrock Knowledge Base (WarrantyAI-KB):
Type: VECTOR (S3 Vectors backed)
Embedding Model: Amazon Titan Text Embeddings v2
Embedding Dimension: 256 (matches index)

ocr.py — Lambda Function
Flow:

SQS Event Parsing: Unwraps S3 event from SQS body
Duplicate Check: Skips .txt and .json files (prevents re-processing)
User Isolation: Extracts user_id from path (uploads/user_123/...)
OCR: Calls Textract on the document
LLM Structuring: Sends OCR text to Mistral 7B
Metadata Sidecar: Saves .metadata.json with user_id and structured data
Text Storage: Saves .txt for Bedrock Knowledge Base
Error Handling: Raises exceptions to trigger SQS retries

### Cost Optimization
S3 Vectors vs OpenSearch: ~70% cheaper for document-scale workloads
Pay-per-request DynamoDB: No capacity management needed
Lambda on-demand: Only runs when documents are uploaded

### Key Innovations in Week 3
Feature	Benefit
Textract Integration	Handles blurry/skewed real-world documents
LLM Structuring	Converts messy OCR into clean JSON facts
S3 Vectors	70% cheaper than OpenSearch for same scale
Metadata Isolation	Prevents cross-tenant data leakage
Event-Driven	Auto-processes uploads; no manual triggers
Error Retries	SQS visibility timeout ensures resilience

### Tags
#MLOps #AWSBedrock #OCR #Textract #VectorDB #S3Vectors #ServerlessRAG #AIPlatformEngineer #WarrantyAI #Terraform