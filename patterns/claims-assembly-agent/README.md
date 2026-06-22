# Claims Assembly Agent

Validates healthcare claim data and assembles compliant EDI 837P professional claim structures using deterministic schema validation and a Bedrock Knowledge Base of payer-specific rules.

## What it does

Given patient, provider, and service data, the agent:

1. Validates all required fields against HIPAA 5010 standards (NPI format, ICD-10 codes, CPT codes, dates, charges)
2. Queries the **validation rules knowledge base** (`query_validation_rules`) for payer-specific requirements (e.g. Medicare prior auth rules, modifier requirements)
3. Assembles a complete **EDI 837P JSON structure** with all required loops and segments (NM1, CLM, DTP, SV1, etc.)
4. Returns validation results with specific error messages for any issues found

## Example prompts

```
Validate this claim: patient John Doe DOB 1980-01-15 member ID MEM123456,
billing provider NPI 1234567890 Tax ID 12-3456789,
diagnosis E11.9, procedure 99213, place of service 11,
date of service 2026-06-01, charge $150.
```
→ Reports validation pass or lists specific field errors

```
Assemble an EDI 837P claim: patient Jane Smith DOB 1975-03-20 member ID ABC123,
provider NPI 1234567890 Tax ID 12-3456789,
procedure 99214 date 2026-06-10 charge $200 diagnosis I10.
```
→ Returns full EDI 837P JSON with CLM, NM1, SV1, DTP segments

```
What are the Medicare-specific requirements for submitting CPT 72148 (MRI lumbar spine)?
```
→ Queries KB and returns prior auth requirements, documentation rules

```
Assemble a claim with two service lines: procedure 99214 charge $200 and ECG 93000 charge $75,
both for diagnosis I10 on 2026-06-18.
```
→ Returns EDI 837P with both SV1 service lines

## Validation checks

| Check | Example error |
|---|---|
| NPI format | Must be exactly 10 digits |
| CPT format | Must be exactly 5 digits |
| ICD-10 format | Must be 3–7 characters |
| Required fields | Diagnosis code required on all claims |
| HIPAA 5010 | Loop and segment completeness |
| Payer rules | KB lookup for payer-specific modifiers, auth requirements |

## Knowledge Base Data

The validation rules knowledge base is pre-loaded with **sample reference data** for demonstration purposes:

- `validation-schemas/` — sample EDI 837P field requirements
- `payer-requirements/` — sample payer-specific rules for common payers
- `compliance-rules/` — sample HIPAA 5010 compliance rules

> **Important:** This is sample data only. Customers deploying this agent should replace the contents of the validation KB S3 bucket with their actual payer contracts, current HIPAA transaction standards, and payer-specific EDI requirements before using in production.

## Sample call

```python
import json
import boto3

payload = {
    "prompt": "Assemble an EDI 837P claim: patient Jane Smith DOB 19750320 "
              "member ID ABC123, provider NPI 1234567890 Tax ID 123456789, "
              "procedure 99214 date 20260610 charge $200 diagnosis I10. "
              "Payer UnitedHealthcare ID 87726.",
    "userId": "biller-001",
    "runtimeSessionId": "session-claims-001"
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
cd patterns/claims-assembly-agent
python claims_assembly_agent.py
# Then POST to the local endpoint:
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What are the Medicare-specific requirements for submitting CPT 72148?",
    "userId": "biller-001",
    "runtimeSessionId": "session-001"
  }'
```
