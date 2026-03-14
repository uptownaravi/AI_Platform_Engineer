# warrantyAI — Week 10
# Container image for Lambda deployment via ECR
#
# Base: AWS Lambda Python 3.12 (ARM64 — Graviton, 20% cheaper than x86)
# Contents: all LangGraph agents + runtime dependencies
#
# Build:
#   docker build -t warrantyai-pipeline .
#
# Run locally (simulate Lambda):
#   docker run -p 9000:8080 \
#     -e AWS_REGION=ap-south-1 \
#     -e WARRANTY_SNS_TOPIC_ARN=arn:aws:sns:... \
#     -e AUDIT_BUCKET=warrantyai-audit-logs \
#     -e HITL_TABLE_NAME=warrantyai-hitl-queue \
#     -e HITL_API_BASE_URL=https://... \
#     -e REVIEW_SNS_TOPIC_ARN=arn:aws:sns:... \
#     warrantyai-pipeline
#
#   # Test invoke:
#   curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
#     -d '{"s3_key":"tenants/t001/doc.pdf","document_id":"test_001","tenant_id":"t001"}'

FROM public.ecr.aws/lambda/python:3.12-arm64

ARG BUILD_DATE=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.title="warrantyAI-pipeline" \
      org.opencontainers.image.description="LangGraph warranty classification pipeline"

WORKDIR ${LAMBDA_TASK_ROOT}

# ── Install Python dependencies ───────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy agent code ───────────────────────────────────────────────────────────
# Reference agents from the warrantyAI/agents/ directory.
# In CI/CD, the repository root is the build context.
COPY warrantyAI/agents/state.py         ./state.py
COPY warrantyAI/agents/graph.py         ./graph.py
COPY warrantyAI/agents/run.py           ./run.py
COPY warrantyAI/agents/resume.py        ./resume.py
COPY warrantyAI/agents/agents/__init__.py ./agents/__init__.py
COPY warrantyAI/agents/agents/reader.py   ./agents/reader.py
COPY warrantyAI/agents/agents/classifier.py ./agents/classifier.py
COPY warrantyAI/agents/agents/reminder.py   ./agents/reminder.py
COPY warrantyAI/agents/agents/hitl.py       ./agents/hitl.py

# ── Lambda entry point ────────────────────────────────────────────────────────
CMD ["run.lambda_handler"]
