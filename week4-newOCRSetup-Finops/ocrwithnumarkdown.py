import boto3
import json
import os

runtime = boto3.client('sagemaker-runtime')
ENDPOINT_NAME = "numarkdown-8b-endpoint"

def lambda_handler(event, context):
    # Parse the prompt from the incoming external request
    body = json.loads(event['body'])
    prompt = body.get('prompt', 'Describe this document.')
    
    # SageMaker expects a specific payload format for Hugging Face containers
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 1024,
            "temperature": 0.1
        }
    }
    
    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType='application/json',
        Body=json.dumps(payload)
    )
    
    result = json.loads(response['body'].read().decode())
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }