import boto3
import json
import os
from datetime import datetime

# Global Clients (Warm Start Optimization)
s3 = boto3.client('s3')
textract = boto3.client('textract')
bedrock = boto3.client('bedrock-runtime')
kb_client = boto3.client('bedrock-agent')

def run_ocr(bucket, key):
    """Visual Layer: Amazon Textract handles messy/blurry real-world documents."""
    try:
        # Try analyze_document for better PDF support
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}},
            FeatureTypes=[]
        )
        return " ".join([b['Text'] for b in response['Blocks'] if b['BlockType'] == 'LINE'])
    except textract.exceptions.UnsupportedDocumentException:
        print(f"Unsupported document format for {key}, skipping OCR.")
        return ""
    except Exception as e:
        print(f"Error in OCR for {key}: {str(e)}")
        return ""

def extract_structured_data(raw_text):
    """Intelligence Layer: Mistral 8B structures the OCR text into JSON facts."""
    if not raw_text:
        return {}
    prompt = f"<s>[INST] Extract Brand, Model, Purchase Date, and Expiry Date as JSON from this text: {raw_text} [/INST]"
    
    body = json.dumps({
        "prompt": prompt,
        "max_tokens": 500,
        "temperature": 0.1
    })
    
    response = bedrock.invoke_model(
        modelId="mistral.mistral-7b-instruct-v0:2", 
        body=body
    )
    
    result = json.loads(response['body'].read())
    # Note: Mistral output might need stripping of markdown backticks
    try:
        return json.loads(result['outputs'][0]['text'])
    except json.JSONDecodeError:
        return {}

def lambda_handler(event, context):
    """The Orchestrator: Triggered by SQS when a document hits S3."""
    print("Received event:", json.dumps(event, indent=2))
    for record in event.get('Records', []):
        try:
            # 1. Parse Event from SQS (S3 event is wrapped in SQS body)
            s3_event = json.loads(record['body'])
            if 'Records' not in s3_event:
                print(f"Unexpected s3_event structure: {json.dumps(s3_event, indent=2)}")
                continue
            bucket = s3_event['Records'][0]['s3']['bucket']['name']
            raw_key = s3_event['Records'][0]['s3']['object']['key']
            
            # Logic: Avoid re-processing the .txt or .json files we generate
            if raw_key.endswith(('.txt', '.json')):
                continue

            # Extract User ID from path (e.g., uploads/user_123/receipt.jpg)
            path_parts = raw_key.split('/')
            user_id = path_parts[1] if len(path_parts) > 1 else "unknown"

            # 2. OCR Visual Extraction
            full_text = run_ocr(bucket, raw_key)
            
            # 3. LLM Semantic Structuring
            structured_data = extract_structured_data(full_text)
            
            # 4. Save Metadata Sidecar (The Isolation Gate for Bedrock)
            metadata_key = f"{raw_key}.metadata.json"
            metadata_body = {
                "metadataAttributes": {
                    "user_id": user_id,
                    "brand": structured_data.get('brand', 'unknown'),
                    "ingested_at": datetime.now().isoformat()
                }
            }
            s3.put_object(Bucket=bucket, Key=metadata_key, Body=json.dumps(metadata_body))
            
            # 5. Save clean text for Bedrock RAG
            s3.put_object(Bucket=bucket, Key=f"{raw_key}.txt", Body=full_text)
            
            # Removed ingestion job trigger as data source is not used with S3_VECTORS
            
            print(f"✅ Successfully processed {raw_key} for User {user_id}")

        except Exception as e:
            print(f"❌ Critical Failure: {str(e)}")
            # Raising the exception ensures SQS retries the message
            raise e

    return {"statusCode": 200, "body": "Processing Complete"}