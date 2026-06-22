# Medical Coding Agent

Extracts standardized medical codes from clinical text using Amazon Comprehend Medical for entity recognition and a Bedrock Knowledge Base for code lookup.

## What it does

Given free-text clinical notes, the agent:

1. Calls **Comprehend Medical** (`extract_medical_entities`) to identify conditions, medications, procedures, and anatomy
2. Searches the **medical codes knowledge base** (`search_medical_codes`) for ICD-10-CM, CPT, and SNOMED CT codes matching each entity
3. Returns codes with descriptions and usage guidance, considering clinical context (e.g. rule-out vs confirmed diagnosis, laterality, procedure type)
4. Optionally detects **PHI** (`detect_phi`) in clinical text

## Example prompts

```
Extract diagnosis codes from: Patient presents with acute exacerbation of COPD.
Started on prednisone taper and albuterol nebulizer.
```
→ Returns J44.1 (COPD with acute exacerbation)

```
What CPT code for a colonoscopy with snare polypectomy of an 8mm sessile sigmoid polyp?
```
→ Returns 45385

```
Perform complete medical coding for: 65-year-old with type 2 diabetes and CKD stage 3, eGFR 45.
```
→ Returns E11.22 (T2DM with CKD) + N18.3 (CKD stage 3)

```
Detect PHI in: Patient John Doe, DOB 01/15/1980, MRN 987654.
```
→ Flags name, date of birth, and MRN as protected health information

## Supported code types

| Type | System | Use |
|---|---|---|
| ICD-10-CM | Diagnoses | Conditions, symptoms, history, screening |
| CPT | Procedures | Office visits, surgery, imaging, labs |
| SNOMED CT | Clinical terms | Interoperability, terminology mapping |

## Key coding rules the agent applies

- **Rule-out / unconfirmed** diagnoses → symptom code (e.g. R07.9 chest pain), not definitive (e.g. not I21 MI)
- **History vs active** → Z85 personal history codes for surveillance visits, not active C-codes
- **Laterality** → right vs left specific codes (M17.11 right knee OA, not M17.12 left)
- **Combination codes** → E11.22 covers both T2DM and CKD together; N18.3 added separately for stage
- **Adverse effects** → T-codes for drug reactions (not poisoning codes unless intentional)

## Knowledge Base Data

The medical codes knowledge base is pre-loaded with **sample reference data** for demonstration purposes, covering a subset of ICD-10-CM, CPT, and SNOMED CT codes.

> **Important:** This is sample data only. Customers deploying this agent should replace the contents of the medical codes KB S3 bucket with licensed, current-year code sets from the appropriate authorities (CMS for ICD-10-CM, AMA for CPT, SNOMED International for SNOMED CT) before using in production.

## Sample call

```python
import json
import boto3

payload = {
    "prompt": "Extract diagnosis and procedure codes from this note: "
              "65-year-old male presents with acute exacerbation of COPD. "
              "Started on prednisone 40mg taper and albuterol nebulizer q4h. "
              "Chest X-ray shows hyperinflation, no infiltrate.",
    "userId": "coder-001",
    "runtimeSessionId": "session-coding-001"
}

# Via AgentCore Runtime API
client = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
response = client.invoke_agent(
    agentId="<your-agent-id>",
    agentAliasId="<your-alias-id>",
    sessionId=payload["runtimeSessionId"],
    inputText=payload["prompt"]
)

for event in response["completion"]:
    if "chunk" in event:
        print(event["chunk"]["bytes"].decode())
```

```bash
# Or via the local development entrypoint
cd patterns/medical-coding-agent
python medical_coding_agent.py
# Then POST to the local endpoint:
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What CPT code for a colonoscopy with snare polypectomy of an 8mm sessile sigmoid polyp?",
    "userId": "coder-001",
    "runtimeSessionId": "session-001"
  }'
```
