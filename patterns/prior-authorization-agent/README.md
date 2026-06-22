# Prior Authorization Agent

Automates healthcare prior authorization workflows by gathering clinical evidence from HealthLake, checking payor policy requirements, assessing medical necessity, and generating FHIR Da Vinci PAS Bundles and ClaimResponses.

## What it does

Given a procedure and patient, the agent:

1. Checks if the procedure requires prior authorization via **payor policy tools** (`lookup_prior_auth_requirements`, `search_payor_policies`)
2. Retrieves patient clinical data from **HealthLake** (conditions, medications, observations, allergies) via Gateway MCP tools
3. Assesses **medical necessity** by cross-referencing clinical evidence against payor-specific coverage criteria
4. Assembles a **FHIR PAS Bundle** (`build_pas_claim_bundle`) containing the Claim (use=preauthorization) and all referenced supporting resources
5. Generates a **FHIR ClaimResponse** (`generate_claim_response`) with the authorization decision (approved/denied/pended)
6. Provides a structured summary with eligibility, clinical evidence, policy requirements, and next steps

## Example prompts

```
Submit prior auth for patient P001 for MRI lumbar spine (CPT 72148).
Patient has 8 weeks of low back pain, failed physical therapy and NSAIDs.
```
→ Retrieves clinical data, checks payor policy, assembles PAS Bundle, recommends approval with evidence

```
Does CPT 27447 (total knee arthroplasty) require prior auth for UnitedHealthcare?
```
→ Looks up payor requirements, returns yes/no with documentation requirements

```
Check prior auth requirements for patient P002 — referral to out-of-network specialist for cardiology consultation.
```
→ Retrieves coverage, checks network status, identifies auth requirements for OON referral

```
Patient P003 needs Humira (adalimumab) for rheumatoid arthritis. Check if prior auth is needed and gather supporting evidence.
```
→ Checks biologic medication auth requirements, gathers relevant labs (RF, anti-CCP, ESR/CRP), prior DMARD failures

```
Generate a prior auth request for patient P001 for spinal fusion surgery (CPT 22612).
Include all supporting clinical documentation.
```
→ Full workflow: eligibility check, clinical evidence assembly, medical necessity assessment, PAS Bundle generation, ClaimResponse

## FHIR resources generated

| Resource | Purpose |
|---|---|
| Claim (use=preauthorization) | The authorization request with service items, diagnoses, and supporting info |
| Bundle (type=collection) | PAS Bundle containing the Claim and all referenced resources |
| ClaimResponse | The authorization decision with outcome, preAuthRef, or error codes |
| Patient, Practitioner, Coverage, Organization | Referenced resources included in the Bundle |

## Gateway tools (via MCP)

| Tool | Data Retrieved |
|---|---|
| `get_patient_conditions` | Diagnoses (ICD-10) supporting medical necessity |
| `get_patient_medications` | Current/historical medications (conservative treatment evidence) |
| `get_patient_observations` | Lab results, imaging, vitals |
| `get_patient_allergies` | Allergy/intolerance records |
| `get_patient_everything` | Comprehensive patient record |
| `advanced_patient_search` | Find patient by demographics |
| `search_payor_policies` | Payor coverage criteria and documentation requirements |
| `lookup_prior_auth_requirements` | Whether a CPT/HCPCS code requires prior auth |
| `handle_order_select` | CDS Hooks integration for EHR order triggers |

## Sample call

```python
import json
import boto3

# Invoke the agent via AgentCore runtime
payload = {
    "prompt": "Submit prior auth for patient P001 for MRI lumbar spine (CPT 72148). "
              "Patient has 8 weeks of low back pain, failed PT and NSAIDs.",
    "userId": "provider-123",
    "runtimeSessionId": "session-abc-001"
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
cd patterns/prior-authorization-agent
python prior_authorization_agent.py
# Then POST to the local endpoint:
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Does CPT 72148 require prior auth for Aetna?",
    "userId": "provider-123",
    "runtimeSessionId": "session-001"
  }'
```

## Security

- **Bedrock Guardrails** — prompt attack filtering (HIGH), healthcare denied topics, PII output filtering for HIPAA identifiers
- **Input sanitization** — all user prompts are sanitized via `prompt_sanitizer.py` before reaching the model
- **PHI logging** — user query content is never logged (only length); access tokens are not logged
