# Appeals Agent

Analyzes denied healthcare claims, retrieves supporting clinical guidelines and payer-specific appeal regulations, generates compliant appeal letters, and saves them to S3.

## What it does

Given a claim denial, the agent:

1. Looks up the **CARC/RARC denial code** (`search_denial_codes`) and explains what it means and what evidence is required to appeal
2. Retrieves **payer-specific appeal deadlines and filing requirements** (`search_appeal_regulations`) — timely filing windows, required forms, escalation paths
3. Finds **clinical guidelines** (`search_clinical_guidelines`) supporting medical necessity for the procedure
4. Generates a structured, evidence-based **appeal letter** using `appeal_letter_builder` (validates all required components: patient, provider, denial info, clinical rationale)
5. Checks filing deadlines via `deadline_tracker` and warns if the window is closing or has passed
6. Saves the finalized letter to S3 (`save_appeal_letter`) and returns a presigned download URL

## Example prompts

```
Claim denied with CARC 50 (not medically necessary) for MRI lumbar spine (CPT 72148).
Patient has 8 weeks of low back pain, failed PT and NSAIDs. What appeal strategy do you recommend?
```
→ Looks up CO-50, retrieves clinical criteria, recommends peer-to-peer review or clinical appeal with guidelines

```
Generate an appeal letter: claim CLM-2026-001 denied CO-50 for CPT 72148.
Patient 8 weeks low back pain, failed PT and NSAIDs.
Provider Dr. Smith NPI 1234567890. Payer Aetna. Denial date 2026-05-15.
Please save the letter to S3.
```
→ Generates complete appeal letter and returns presigned S3 URL for download

```
What is the appeal filing deadline for Aetna? Denial date was 2026-05-01.
```
→ Returns payer-specific deadline (e.g. 180 days) and calculated due date

```
Claim denied CO-29 (timely filing exceeded). Original submission was 2026-02-01.
Provider has proof of timely filing. Generate appeal.
```
→ Generates timely filing appeal citing proof of original submission date

```
Claim denied with both CO-4 (procedure not covered for diagnosis) and CO-97 (bundled).
Procedure 93000, diagnosis I10. What are my appeal options?
```
→ Analyzes both denial codes and outlines separate appeal strategies for each

## Appeal letter components

The agent validates that every letter includes:

| Component | Example |
|---|---|
| Patient info | Name, DOB, member ID |
| Provider info | Name, NPI, contact |
| Denial info | Claim ID, denial date, CARC code, payer name |
| Date of service | Service date |
| Clinical rationale | Evidence-based justification (≥ 50 characters) |
| Requested action | Specific ask (approve auth, reprocess claim, etc.) |
| Supporting documents | List of attachments |

## Knowledge Base Data

The appeals knowledge base is pre-loaded with **sample reference data** for demonstration purposes:

- `denial-codes/` — sample CARC/RARC codes with appeal strategies
- `appeal-regulations/` — sample payer filing timelines and requirements
- `clinical-guidelines/` — sample medical necessity criteria

> **Important:** This is sample data only. Customers deploying this agent should replace the contents of the appeals KB S3 bucket with their own payer contracts, actual CARC/RARC code libraries, payer-specific appeal filing rules, and clinical guideline references before using in production.

## Sample call

```python
import json
import boto3

payload = {
    "prompt": "Claim CLM-2026-001 denied CARC 50 for MRI lumbar spine (CPT 72148). "
              "Patient has 8 weeks low back pain, failed PT and NSAIDs. "
              "Provider Dr. Smith NPI 1234567890. Payer Aetna. Denial date 2026-05-15. "
              "Generate an appeal letter and save to S3.",
    "userId": "billing-staff-001",
    "runtimeSessionId": "session-appeal-001"
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
cd patterns/appeals-agent
python appeals_agent.py
# Then POST to the local endpoint:
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the appeal filing deadline for Aetna? Denial date was 2026-05-01.",
    "userId": "billing-staff-001",
    "runtimeSessionId": "session-001"
  }'
```
