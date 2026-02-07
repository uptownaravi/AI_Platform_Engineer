import boto3
import json
import os
import time
import re
from datetime import datetime

s3 = boto3.client('s3')
textract = boto3.client('textract')
bedrock = boto3.client('bedrock-runtime')
runtime = boto3.client('sagemaker-runtime')
cw = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb').Table(os.environ.get('TABLE_NAME', 'WarrantyAI-Metadata'))

def run_ocr_async(bucket, key):
    """Handles multi-page PDFs by polling Textract Async API."""
    response = textract.start_document_text_detection(
        DocumentLocation={'S3Object': {'Bucket': bucket, 'Name': key}}
    )
    job_id = response['JobId']
    
    while True:
        status_resp = textract.get_document_text_detection(JobId=job_id)
        status = status_resp['JobStatus']
        if status in ['SUCCEEDED', 'FAILED']:
            break
        time.sleep(2)
        
    if status == 'FAILED': return ""

    pages = []
    next_token = None
    while True:
        kwargs = {'JobId': job_id}
        if next_token: kwargs['NextToken'] = next_token
        res = textract.get_document_text_detection(**kwargs)
        pages.append(" ".join([b['Text'] for b in res['Blocks'] if b['BlockType'] == 'LINE']))
        next_token = res.get('NextToken')
        if not next_token: break
    return " ".join(pages)

def refine_with_numarkdown(raw_text):
    """Calls SageMaker NuMarkdown-8B to clean OCR into high-fidelity Markdown."""
    payload = {
        "inputs": f"<think>Organize warranty tables and clauses.</think> Convert to Markdown: {raw_text[:8000]}",
        "parameters": {"max_new_tokens": 1024, "temperature": 0.1}
    }
    start_time = time.time()
    response = runtime.invoke_endpoint(
        EndpointName="numarkdown-8b-endpoint",
        ContentType='application/json',
        Body=json.dumps(payload)
    )
    latency = (time.time() - start_time) * 1000
    
    # FinOps: Log SageMaker Latency
    cw.put_metric_data(
        Namespace='WarrantyAI/FinOps',
        MetricData=[{'MetricName': 'NuMarkdownLatency', 'Value': latency, 'Unit': 'Milliseconds'}]
    )
    return json.loads(response['body'].read().decode())[0]['generated_text']

# WEEK 5 CORE: SEMANTIC ACTION LOGIC 

def check_eligibility_logic(zip_code, is_beyond_limit):
    """
    Implements the hard logic found in lgrefrigeratorwarrany.pdf.
    """
    
    status = "ACTION_REQUIRED" if is_beyond_limit else "STANDARD"
    
    message = (
        "According to your warranty terms: "
        "1. Since you are outside municipal limits, you must bring the unit to the center at your own cost/risk. "
        "2. Travel expenses for technicians will be charged to you[cite: 17, 83]. "
        if is_beyond_limit else 
        "You are within municipal limits. Standard visiting charges still apply per policy[cite: 82, 84]."
    )
    
    return {
        "eligibility_status": status,
        "policy_notes": message,
        "reference": "LG Warranty Page 1 & 4"
    }

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
    # PATH A: SQS Trigger (Ingestion Pipeline)
    if 'Records' in event:
        for record in event['Records']:
            s3_data = json.loads(record['body'])['Records'][0]['s3']
            bucket, key = s3_data['bucket']['name'], s3_data['object']['key']
            
            if key.endswith(('.txt', '.json')): continue
            
            # Step 1: OCR
            raw_text = run_ocr_async(bucket, key)
            
            # Step 2: Reasoning Refinement
            clean_markdown = refine_with_numarkdown(raw_text)
            
            # Step 3: Persistence for RAG
            user_id = key.split('/')[1] if '/' in key else "unknown"
            s3.put_object(Bucket=bucket, Key=f"{key}.txt", Body=clean_markdown)
            
            # Metadata for Isolation
            metadata = {"metadataAttributes": {"user_id": user_id, "brand": "LG"}}
            s3.put_object(Bucket=bucket, Key=f"{key}.metadata.json", Body=json.dumps(metadata))
            
        return {"statusCode": 200, "body": "Ingestion Success"}

    # PATH B: Bedrock Agent Trigger (Semantic Action)
    else:
        action_group = event.get('actionGroup')
        api_path = event.get('apiPath')
        
        if api_path == "/verify-service-area":
            # Extract params passed by Agent reasoning
            params = {p['name']: p['value'] for p in event.get('parameters', [])}
            zip_code = params.get('zip_code', 'unknown')
            
            # Mock distance check logic
            is_beyond = True # In production, check against a Service Center DB
            
            result = check_eligibility_logic(zip_code, is_beyond)
            
            response_body = {'application/json': {'body': json.dumps(result)}}
            return {
                'messageVersion': '1.0',
                'response': {
                    'actionGroup': action_group,
                    'apiPath': api_path,
                    'httpStatusCode': 200,
                    'responseBody': response_body
                }
            }

    return {"statusCode": 400, "body": "Unknown Event Source"}