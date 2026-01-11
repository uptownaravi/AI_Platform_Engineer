# Warranty AI — AI Platform Engineer Learning Repo

Transition from Cloud Engineer to AI Platform Engineering.
My north-star for 2026 is to build Warranty AI — a production-grade, "warranty-aware" system that helps homeowners and office managers assess appliance health, identify "fine-print" gotchas, and optimize repair costs using Generative AI and semantic search.

## The Year-Long Vision: Why an AI Platform Engineer?
An AI Platform Engineer builds the scalable plumbing that allows AI models to interact with real-world data securely and efficiently. The 12-month roadmap focuses on:
- **MLOps:** Automating model lifecycle (train, deploy, monitor).
- **Semantic Architecture:** Vector databases for long-term memory.
- **Cloud-Native AI:** AWS Bedrock + S3 lakehouses for scale and cost control.

Repository layout:
- week1-setup-vector/: Week 1 materials and prototype code
  - [week1-setup-vector/warranty_ai.py](week1-setup-vector/warranty_ai.py)
  - [week1-setup-vector/README.md](week1-setup-vector/README.md)

Quickstart (local):
1. Create virtualenv and activate:
   - `python3 -m venv venv`
   - `source venv/bin/activate`
2. Install required packages:
   - `pip install boto3 pymupdf faiss-cpu numpy`
3. Run the Week 1 script:
   - `python week1-setup-vector/warranty_ai.py`

Notes:
- You need AWS credentials configured with Bedrock access and `bedrock:InvokeModel` permissions.
- Region used in examples: `ap-south-1`.

## Tags
#MLOps #AWSBedrock #AIPlatformEngineer #WarrantyAI #GenerativeAI #DevOpsToAI #ApacheIceberg
