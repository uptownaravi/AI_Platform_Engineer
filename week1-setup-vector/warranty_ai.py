import boto3
import json
import fitz
import numpy as np
import faiss

# 1. Setup Clients
REGION = "ap-south-1"
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

# 2. Function to get Embeddings from Titan v2
def get_embedding(text):
    native_request = {"inputText": text}
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps(native_request)
    )
    return json.loads(response["body"].read())["embedding"]

# 3. Process PDF into Semantic Chunks
doc = fitz.open("./data/lgrefrigeratorwarranty.pdf")
pages_text = [page.get_text() for page in doc]
# Convert each page into a vector
page_embeddings = [get_embedding(p) for p in pages_text]

# 4. Create the Vector Index (The 'Ops' part)
dimension = len(page_embeddings[0]) # Titan v2 is usually 1024
index = faiss.IndexFlatL2(dimension)
index.add(np.array(page_embeddings).astype('float32'))

# 5. Semantic Retrieval
user_query = "What is the compressor warranty period?"
query_vector = get_embedding(user_query)

# Search for the top 1 most relevant page
D, I = index.search(np.array([query_vector]).astype('float32'), k=1)
relevant_page_text = pages_text[I[0][0]]

# 6. Final LLM Generation (using the relevant chunk only)
native_request = {
    "messages": [{"role": "user", "content": f"Context: {relevant_page_text}\nQuestion: {user_query}"}],
    "max_tokens": 512, "temperature": 0.2
}
response = bedrock.invoke_model(
    modelId="mistral.ministral-3-8b-instruct",
    body=json.dumps(native_request)
)
print(json.loads(response["body"].read())["choices"][0]["message"]["content"])