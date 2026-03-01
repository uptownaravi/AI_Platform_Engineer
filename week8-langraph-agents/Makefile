REGION    ?= ap-south-1
EMAIL     ?= $(NOTIFICATION_EMAIL)
DOCS_BUCKET ?= warrantyai-documents

.PHONY: build-layer deploy plan test run-local clean

## Build Lambda layer for LangGraph deps (run BEFORE deploy)
## Creates infra/deps.zip with langgraph + langchain-core for linux/arm64
build-layer:
	@echo "Building LangGraph Lambda layer for linux/arm64..."
	rm -rf /tmp/week8-layer && mkdir -p /tmp/week8-layer/python
	pip install -r requirements.txt \
	  -t /tmp/week8-layer/python \
	  --platform linux_aarch64 \
	  --only-binary=:all: \
	  --quiet
	cd /tmp/week8-layer && zip -r $(CURDIR)/infra/deps.zip python/ -q
	@echo "Layer built: infra/deps.zip"

## Preview Terraform changes
plan: build-layer
	cd infra && terraform init && terraform plan \
	  -var="warranty_docs_bucket_name=$(DOCS_BUCKET)" \
	  -var="notification_email=$(EMAIL)"

## Deploy Week 8 infra (SNS + Lambda + IAM + S3 trigger)
deploy: build-layer
	cd infra && terraform init && terraform apply -auto-approve \
	  -var="warranty_docs_bucket_name=$(DOCS_BUCKET)" \
	  -var="notification_email=$(EMAIL)"
	@echo ""
	@echo "Week 8 deployed. Outputs:"
	@cd infra && terraform output

## Remove generated zip files and cache
clean:
	rm -f infra/deps.zip infra/pipeline_code.zip
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
