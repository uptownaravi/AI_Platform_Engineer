REGION        ?= ap-south-1
FUNCTION_NAME ?= warrantyai-langgraph-pipeline
ACCOUNT_ID    := $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "000000000000")

.PHONY: test test-latency test-cost regression update-baseline \
        deploy-infra status canary promote rollback dashboard traces \
        lint clean help

## Run prompt regression suite (requires AWS Bedrock access)
test:
	pytest tests/test_regression.py -v --tb=short

## Run latency benchmark (10 fixtures · p95 < 8s)
test-latency:
	pytest tests/test_latency.py -v --tb=short -s

## Run token cost baseline check (20 fixtures)
test-cost:
	pytest tests/test_cost_baseline.py -v --tb=short -s

## Run regression + latency + cost (full CI suite)
test-all:
	pytest tests/ -v --tb=short -s

## Update token baseline after an intentional prompt change
update-baseline:
	@echo "Running all 20 fixtures to measure actual token usage..."
	@python -c "\
import json, glob, os, sys; \
sys.path.insert(0, '.'); \
from agents.classifier import run_classifier; \
fixtures = sorted(glob.glob('tests/fixtures/*.json')); \
results = {}; \
total = 0; \
for p in fixtures: \
  f = json.load(open(p)); \
  r = run_classifier(f['input']['document_text'], f['input'].get('tenant_id','update')); \
  results[f['document_id']] = r['usage']['total_tokens']; \
  total += r['usage']['total_tokens']; \
  print(f\"  {f['document_id']:20s}  {r['usage']['total_tokens']:>6d} tokens\"); \
avg = total // len(fixtures); \
baseline = json.load(open('tests/baselines/token_baseline.json')); \
baseline['avg_tokens_per_doc'] = avg; \
baseline['alert_threshold'] = int(avg * 1.20); \
baseline['per_fixture'] = results; \
json.dump(baseline, open('tests/baselines/token_baseline.json','w'), indent=2); \
print(f'\nBaseline updated: avg={avg} tokens/doc  alert_threshold={int(avg*1.20)}'); \
print('Commit the updated baseline: git add tests/baselines/token_baseline.json'); \
"

## Deploy CloudWatch dashboard + Lambda aliases
deploy-infra:
	cd infra && terraform init && terraform apply \
	  -var="lambda_function_name=$(FUNCTION_NAME)" \
	  -var="aws_region=$(REGION)"

## Show staging and production alias versions
status:
	python scripts/promote_canary.py --status

## Route 10% of production traffic to staging (canary)
canary:
	python scripts/promote_canary.py --canary 10

## Promote staging to production (100% traffic shift)
promote:
	python scripts/promote_canary.py --promote

## Rollback production to a specific version
## Usage: make rollback VERSION=3
rollback:
	python scripts/promote_canary.py --rollback $(VERSION)

## Open CloudWatch observability dashboard (macOS/Linux)
dashboard:
	@URL="https://$(REGION).console.aws.amazon.com/cloudwatch/home?region=$(REGION)#dashboards:name=warrantyai-observability"; \
	  echo "Dashboard: $$URL"; \
	  command -v xdg-open >/dev/null 2>&1 && xdg-open "$$URL" || \
	  command -v open >/dev/null 2>&1 && open "$$URL" || \
	  echo "Open the URL above in your browser"

## Open LangSmith project traces
traces:
	@echo "LangSmith: https://smith.langchain.com/projects/warrantyai-production"
	@command -v xdg-open >/dev/null 2>&1 && xdg-open "https://smith.langchain.com/projects/warrantyai-production" || \
	  command -v open >/dev/null 2>&1 && open "https://smith.langchain.com/projects/warrantyai-production" || true

## Lint Python files
lint:
	python -m py_compile \
	  agents/classifier.py \
	  observability/langsmith_tracer.py \
	  observability/cloudwatch_metrics.py \
	  tests/test_latency.py \
	  tests/test_cost_baseline.py \
	  scripts/promote_canary.py
	@echo "Syntax OK"

## Remove generated artefacts
clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -f regression_report.txt regression-results.xml latency_report.txt latency-results.xml smoke_response.json

help:
	@grep -E '^## ' Makefile | sed 's/## /  /'
