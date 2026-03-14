REGION      ?= ap-south-1
ACCOUNT_ID  := $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "000000000000")
GITHUB_ORG  ?= your-org
GITHUB_REPO ?= warrantyai

.PHONY: test regression lint build push setup-oidc clean help

## Run the full prompt regression suite (requires AWS Bedrock access)
test:
	pytest tests/test_regression.py -v --tb=short

## Run only the overall accuracy gate (fast — single pass through all fixtures)
regression:
	pytest tests/test_regression.py::test_overall_accuracy -v --tb=short

## Run tests in parallel (faster — runs each fixture concurrently)
test-parallel:
	pytest tests/test_regression.py -v --tb=short -n auto

## Show fixture count and risk level distribution
fixtures:
	@echo "Fixture distribution:"
	@python -c "import json,glob; fs=[json.load(open(p)) for p in sorted(glob.glob('tests/fixtures/*.json'))]; \
	  low=sum(1 for f in fs if f['expected']['risk_level']=='low'); \
	  med=sum(1 for f in fs if f['expected']['risk_level']=='medium'); \
	  hi=sum(1 for f in fs if f['expected']['risk_level']=='high'); \
	  print(f'  LOW:    {low}'); print(f'  MEDIUM: {med}'); print(f'  HIGH:   {hi}'); \
	  print(f'  TOTAL:  {len(fs)}')"

## Lint Python files
lint:
	python -m py_compile agents/classifier.py tests/test_regression.py
	@echo "Syntax OK"

## Build Docker image (from repo root — Dockerfile copies from warrantyAI/)
build:
	cd ../.. && docker build \
	  --build-arg GIT_COMMIT=$(shell git rev-parse --short HEAD 2>/dev/null || echo dev) \
	  -t $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com/warrantyai-pipeline:latest \
	  -f week10-cicd-regression/Dockerfile .

## Push to ECR (requires aws ecr get-login-password first)
push: build
	aws ecr get-login-password --region $(REGION) | \
	  docker login --username AWS --password-stdin $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com
	docker push $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com/warrantyai-pipeline:latest

## Deploy OIDC IAM role + ECR repository (run once)
setup-oidc:
	cd infra && terraform init && terraform apply \
	  -var="github_org=$(GITHUB_ORG)" \
	  -var="github_repo=$(GITHUB_REPO)"
	@echo ""
	@echo "Copy these values to GitHub Secrets:"
	@cd infra && terraform output github_actions_role_arn
	@cd infra && terraform output ecr_registry

## Remove generated artefacts
clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -f regression_report.txt regression-results.xml

help:
	@grep -E '^## ' Makefile | sed 's/## /  /'
