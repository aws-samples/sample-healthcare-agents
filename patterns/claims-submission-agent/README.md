# Claims Submission Agent

Submits EDI 837P claims to payers via **AWS B2B Data Interchange**, tracks transformation job status, and retrieves 997/999 functional acknowledgments.

## What it does

Given an assembled EDI 837P claim, the agent:

1. Submits the claim JSON to the B2BI input S3 bucket (`submit_claim`) and returns a job/tracking ID
2. Queries transformation job status (`check_submission_status`) for a given job ID
3. Retrieves **997/999 functional acknowledgments** (`retrieve_acknowledgments`) from payers — accepted or rejected with reason codes
4. Lists recent submission history (`list_submissions`) for audit and tracking
5. Handles resubmissions and explains rejection reasons

## Example prompts

```
Submit this EDI 837P claim to the payer:
{"trading_partner": "AETNA", "patient_id": "PAT001", "procedure": "99213",
 "diagnosis": "I10", "provider_npi": "1234567890", "charge": 150.00,
 "date_of_service": "2026-06-18", "member_id": "AET123456"}
```
→ Returns B2BI job ID and submission confirmation

```
Check the status of claim submission job ID job-abc-12345.
```
→ Returns current transformation job status (PENDING, PROCESSING, COMPLETED, FAILED)

```
Retrieve the 997 functional acknowledgment for claim submission CLM-001.
```
→ Returns acceptance or rejection with TA1/AK2 segment details

```
List my recent claim submissions from the past week.
```
→ Returns submission history with job IDs, statuses, and timestamps

## B2BI workflow

```
Claim JSON → submit_claim → B2BI Input Bucket
                                    ↓
                          B2B Data Interchange (EDI transform)
                                    ↓
                          Payer → 997/999 Acknowledgment
                                    ↓
                     retrieve_acknowledgments → accepted / rejected
```

## Sample call

```python
import json
import boto3

payload = {
    "prompt": "Submit this claim to Aetna: patient PAT001, procedure 99213, "
              "diagnosis I10, provider NPI 1234567890, charge $150, "
              "date of service 2026-06-18, member ID AET123456.",
    "userId": "biller-001",
    "runtimeSessionId": "session-submit-001"
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
cd patterns/claims-submission-agent
python claims_submission_agent.py
# Then POST to the local endpoint:
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Check the status of claim submission job ID job-abc-12345.",
    "userId": "biller-001",
    "runtimeSessionId": "session-001"
  }'
```
