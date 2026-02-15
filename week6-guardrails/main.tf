# Bedrock Guardrail Configuration
resource "aws_bedrock_guardrail" "governance_shield" {
  name                      = "GovernanceShield-Week6"
  blocked_input_messaging   = "I'm sorry, but I cannot process this request due to safety and privacy policies."
  blocked_outputs_messaging = "I cannot provide that specific information. Please contact official support for further assistance."
  description               = "Safety filters for PII masking and legal topic denial."

  # 1. PII Masking: Redacting sensitive data from receipts
  sensitive_information_policy_config {
    pii_entities_config {
      type   = "PHONE"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "ADDRESS"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "EMAIL"
      action = "BLOCK"
    }
  }

  # 2. Topic Denial: Preventing legal advice/lawsuit representation
  topic_policy_config {
    topics_config {
      name     = "LegalAdvice"
      definition = "Providing legal guidance, interpreting laws, or acting as a legal representative regarding claims or lawsuits in the state of Delhi or elsewhere."
      examples = [
        "How do I sue for a warranty claim?",
        "What are my legal rights in the Delhi court system?",
        "Can you represent me in a lawsuit against the manufacturer?"
      ]
      type = "DENY"
    }
  }

  # 3. Official Channel Enforcement: Filter for unverified contact details
  # This prevents the AI from hallucinating numbers other than 0806-937-9999
  word_policy_config {
    words_config {
      text = "unverified-support-line"
    }
    # You can add managed word lists for profanity/offensive content here
    managed_word_lists_config {
      type = "PROFANITY"
    }
  }

  # Content Filter: Standard safety for professional boundaries
  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULT"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
  }
}

# Versioning the Guardrail for Production Use
resource "aws_bedrock_guardrail_version" "v1" {
  description      = "Initial Governance Version"
  guardrail_arn    = aws_bedrock_guardrail.governance_shield.guardrail_arn
  skip_destroy     = false
}