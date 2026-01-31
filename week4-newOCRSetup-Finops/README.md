Week 4 — New OCR Setup (FinOps)
===============================

Overview
--------
This folder contains the Week 4 materials for the "AI Platform Engineer" track focused on a new OCR setup with FinOps and monitoring in mind. It includes a Terraform dashboard for CloudWatch, a SageMaker deployment helper, and an OCR script that produces numbered Markdown output.

Files
-----
- [cloudwatchdashboard.tf](cloudwatchdashboard.tf): Terraform config to provision a CloudWatch dashboard to monitor OCR/Model endpoints and relevant AWS metrics.
- [deployModelToSagemaker.py](deployModelToSagemaker.py): Helper script to package and deploy a model to Amazon SageMaker (examples and required IAM/role notes below).
- [ocrwithnumarkdown.py](ocrwithnumarkdown.py): OCR processing script that extracts text and writes results as numbered Markdown entries.

Quickstart
----------
1. Monitoring (CloudWatch dashboard)
	- Initialize and apply Terraform in this folder to create the dashboard:
	```
	terraform init
	terraform apply
	```
	- Review and customize the dashboard JSON in `cloudwatchdashboard.tf` before applying.

2. Deploy model to SageMaker
	- Ensure your model artifacts are in S3 and you have an execution role for SageMaker.
	- Example run (adjust args in the script or pass needed env vars):
	```
	python deployModelToSagemaker.py --model-s3 s3://my-bucket/path/to/model.tar.gz --role-arn arn:aws:iam::123456789012:role/SageMakerExecRole
	```
	- The script uses the SageMaker APIs and boto3; review it to adapt instance types, endpoint config, and model names.

3. Run OCR and produce numbered Markdown
	- Run the OCR script against local images or S3-hosted images. Example:
	```
	python ocrwithnumarkdown.py --input ./sample-images --output results.md
	```
	- Output: a Markdown file with each detected document/text block numbered for easy review.

FinOps & Operational Notes
--------------------------
- Monitor inference instance usage and endpoint invocation metrics in CloudWatch to control costs.
- Prefer smaller instance types for testing; use autoscaling or multi-model endpoints for cost efficiency.
- Clean up SageMaker endpoints and unused model artifacts to avoid ongoing charges.