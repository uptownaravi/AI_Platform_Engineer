## Week 1 Learning: Breaking the "Black Box"
This week focused on Retrieval-Augmented Generation (RAG). Instead of generic prompts, I fed a specific 5-page LG Refrigerator Warranty PDF and asked the system to find hidden costs.

Core Concepts Mastered:
- **Embeddings (The Translator):** Amazon Titan Text Embeddings v2 to convert text into vectors.
- **Vector Indexing (The Library):** FAISS to store vectors and search by semantic similarity.
- **Messages API (The Conversation):** Structured messages for modern LLMs (e.g., Mistral / Ministral-3-8b).

## The Setup: Prerequisites & Environment

1. AWS Configuration:
- **Region:** `ap-south-1` (Mumbai).
- **Model Access:** Request Bedrock access for Mistral / Ministral-3-8b and Titan Text Embeddings v2.
- **IAM:** Ensure `bedrock:InvokeModel` permissions for the required model ARNs.

2. Local Environment:
- Create venv and activate:
  - `python3 -m venv venv`
  - `source venv/bin/activate`
- Install packages:
  - `pip install boto3 pymupdf faiss-cpu numpy`

Suggested runtime:
- Python 3.10+
- A machine with enough RAM for FAISS and vector operations.

## Prototype: `week1-setup-vector/warranty_ai.py`
- Loads `./data/lgrefrigeratorwarranty.pdf`
- Embeds pages with Titan v2 via Bedrock
- Indexes with FAISS
- Runs a semantic retrieval for a user query and generates an answer with a LLM via Bedrock

## Conclusion & Next Steps
Week 1 taught me AI engineering is ~20% prompting and ~80% data/infrastructure engineering. Next week: move vectors into a persistent S3 Lakehouse with Apache Iceberg for scale and queryability.

## Tags
#MLOps #AWSBedrock #AIPlatformEngineer #WarrantyAI #GenerativeAI #DevOpsToAI #ApacheIceberg