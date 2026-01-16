# Warranty AI

## Week 2 Overview

Week 2 focues on building the RAG pipeline for the uploaded documents

## Technical Architecture

The platform is built on a Serverless Retrieval-Augmented Generation (RAG) architecture. Unlike Week 1 (Local FAISS), Week 2 uses:

- **Amazon S3**: The "Source of Truth" for raw PDFs and user-specific metadata.
- **Amazon Bedrock Knowledge Bases**: The "Orchestrator" that automates text parsing, chunking, and vector embedding generation.
- **Amazon OpenSearch Serverless**: The high-performance "Vector Store" that persists embeddings and allows for sub-second semantic search.
- **Metadata Isolation**: Every document is tagged with a `user_id`. Queries are pre-filtered at the vector-database level, ensuring User A can never see User B's data.

## Project Structure

- `terraform/main.tf`: Deploys the S3 bucket, OpenSearch Serverless collection, and Bedrock Knowledge Base.
- `upload-and-vector.py`: Handles the secure upload of PDFs along with `.metadata.json` sidecar files to enforce multi-tenancy.
- `retrieve-with-questions.py`: The production-tier RAG loop using the `retrieve_and_generate` API.

## How It Works (Technical Detail)

### 1. Secure Ingestion

When a user uploads a document, two files are sent to S3:

- `warranty_v1.pdf`: The raw document.
- `warranty_v1.pdf.metadata.json`: Contains `{ "metadataAttributes": { "user_id": "user_123" } }`.

### 2. Automated Indexing

The Knowledge Base "Sync" job (triggered via boto3) reads these files. It uses the Titan Text Embeddings v2 model to convert text into mathematical vectors. These vectors are stored in OpenSearch Serverless along with the `user_id` attribute.

### 3. Isolated Retrieval

During a query, we use Metadata Filtering.

- **Request**: "When does my compressor warranty end?" (User: user_123)
- **Process**: Bedrock filters the OpenSearch index for `user_id == 'user_123'` before performing the semantic search.
- **Response**: The LLM receives context only from that user's PDFs, preventing cross-tenant data leakage.

## Setup Instructions

1. **Deploy Infra**: Run `terraform apply` in the `/terraform` folder.
2. **Ingest Data**: Use `python upload-and-vector.py` to upload your LG Refrigerator warranty.
3. **Query AI**: Use `python retrieve-with-questions.py` to ask, "Is gas charging covered?"