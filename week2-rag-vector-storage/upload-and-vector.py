import boto3
import json

s3 = boto3.client('s3')
bedrock_agent = boto3.client('bedrock-agent')

BUCKET = "warrantyai"
KB_ID = "YOUR_KB_ID" # Get from Terraform output
DS_ID = "YOUR_DS_ID"

def upload_and_sync(user_id, file_path, file_name):
    # 1. Upload the PDF
    s3.upload_file(file_path, BUCKET, file_name)
    
    # 2. Upload the Metadata (This enables the user_id filter)
    metadata = {
        "metadataAttributes": {
            "user_id": user_id
        }
    }
    s3.put_object(
        Bucket=BUCKET,
        Key=f"{file_name}.metadata.json",
        Body=json.dumps(metadata)
    )
    
    # 3. Trigger Sync (This moves data from S3 to the Vector DB)
    bedrock_agent.start_ingestion_job(
        knowledgeBaseId=KB_ID,
        dataSourceId=DS_ID
    )
    print(f"🚀 Sync started for {file_name} (User: {user_id})")

upload_and_sync("user_001", "refrigeratorwarrany.pdf", "fridge.pdf")