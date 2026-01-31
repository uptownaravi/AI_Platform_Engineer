import sagemaker
from sagemaker.huggingface import HuggingFaceModel

# Initial Setup
role = "arn:aws:iam::<account-number>:role/SageMakerExecutionRole" # Use your Role ARN
sess = sagemaker.Session()

# Model Configuration
# Note: Using the Hugging Face LLM Inference Container (TGI)
hub = {
    'HF_MODEL_ID': 'numind/NuMarkdown-8B-Thinking',
    'HF_TASK': 'text-generation',
    'SM_NUM_GPUS': '1' 
}

# Create the SageMaker Model
huggingface_model = HuggingFaceModel(
    env=hub,
    role=role,
    transformers_version="4.28", # Ensure compatibility with Qwen 2.5
    pytorch_version="2.0",
    py_version="py310",
)

# Deploy to an Endpoint
# ml.g5.2xlarge is usually the best price/performance for 8B models
predictor = huggingface_model.deploy(
    initial_instance_count=1,
    instance_type="ml.g5.2xlarge",
    endpoint_name="numarkdown-8b-endpoint"
)

print(f"Endpoint deployed: {predictor.endpoint_name}")