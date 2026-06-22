# Eligibility Verification Agent

Verifies patient insurance eligibility and benefits by retrieving coverage data from HealthLake (FHIR R4), checking active status, determining cost sharing, and identifying prior authorization requirements.

## What it does

Given a patient and requested service, the agent:

1. Retrieves **patient demographics and coverage** from HealthLake via Gateway MCP tools
2. Verifies the insurance plan is **active** with valid effective dates
3. Checks if the requested service is a **covered benefit** under the plan
4. Determines **cost sharing** — copay, coinsurance, deductible status, out-of-pocket maximum
5. Identifies whether the service **requires prior authorization**
6. Provides a structured eligibility verification summary with clear next steps

## Example prompts

```
Verify eligibility for patient P001 for an MRI procedure.
```
→ Retrieves patient record, checks active coverage, determines MRI benefits and cost sharing

```
Is patient P002 currently covered? Check their insurance status.
```
→ Returns coverage status, plan type, effective dates, payor information

```
What is the copay and deductible status for patient P001 for an office visit (CPT 99214)?
```
→ Returns copay amount, deductible met/remaining, coinsurance percentage, estimated patient responsibility

```
Does patient P003's plan require prior auth for physical therapy?
```
→ Checks coverage details, identifies PT visit limits, determines if prior auth is needed

```
Search for patient John Doe, DOB 1975-03-20, member ID MEM456789. Verify their eligibility for cardiology consultation.
```
→ Searches patient by demographics, retrieves coverage, checks specialist referral requirements

```
Check eligibility for patient P001 for outpatient surgery. Is the provider in-network?
```
→ Verifies coverage, checks network status, determines out-of-pocket cost difference

## Verification workflow

```
Patient ID / Demographics
         ↓
  HealthLake Lookup (Gateway MCP)
         ↓
  Coverage Status: Active / Inactive
         ↓
  Benefits Check: Covered / Excluded / Limited
         ↓
  Cost Sharing: Copay + Coinsurance + Deductible
         ↓
  Prior Auth Required? Yes / No
         ↓
  Summary + Next Steps
```

## Gateway tools (via MCP)

| Tool | Use Case |
|---|---|
| `get_patient_conditions` | Diagnoses and conditions |
| `get_patient_medications` | Current medications |
| `get_patient_observations` | Lab results, vitals |
| `get_patient_allergies` | Allergy records |
| `get_patient_appointments` | Scheduled/past visits |
| `get_patient_everything` | Full patient record including coverage |
| `advanced_patient_search` | Find patient by name, DOB, member ID |

## Sample call

```python
import json
import boto3

# Invoke the agent via AgentCore runtime
payload = {
    "prompt": "Verify eligibility for patient P001 for an MRI lumbar spine procedure. "
              "Check coverage status, benefits, and whether prior auth is required.",
    "userId": "provider-456",
    "runtimeSessionId": "session-elig-001"
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
cd patterns/eligibility-verification-agent
python eligibility_verification_agent.py
# Then POST to the local endpoint:
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Is patient P001 currently covered? Check their insurance status and plan details.",
    "userId": "provider-456",
    "runtimeSessionId": "session-001"
  }'
```

## Key behaviors

- Always retrieves actual patient data from HealthLake — never assumes coverage status
- Clearly distinguishes between verified data and estimated information
- If coverage data is unavailable, recommends a real-time 270/271 eligibility transaction with the payor
- Follows HIPAA guidelines — minimizes PHI exposure in responses
- Coverage verification is point-in-time — status can change daily
