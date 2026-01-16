runtime = boto3.client("bedrock-agent-runtime", region_name="ap-south-1")

def ask_warranty_ai(user_id, question):
    response = runtime.retrieve_and_generate(
        input={'text': question},
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': KB_ID,
                'modelArn': 'arn:aws:bedrock:ap-south-1::foundation-model/mistral.ministral-3-8b-instruct-v1:0',
                # THE SECURITY GATE: Only look at this user's data
                'retrievalConfiguration': {
                    'vectorSearchConfiguration': {
                        'filter': {
                            'equals': {'key': 'user_id', 'value': user_id}
                        }
                    }
                }
            }
        }
    )
    return response['output']['text']

print(f"AI: {ask_warranty_ai('user_001', 'Is the gas leak covered?')}")