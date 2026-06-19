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

## Tests

### Integration tests (`tests/integration/runtime/TestClaimsSubmissionAgent`)

| Test | What it validates |
|---|---|
| `test_submit_claim_via_b2bi` | Claim submitted to B2BI; response contains job/tracking ID or submission confirmation |
| `test_check_submission_status` | Agent queries and returns job status (pending, complete, processing, or failed) |
| `test_retrieve_997_acknowledgment` | Agent retrieves and interprets 997/999 acknowledgment for a claim |
| `test_list_recent_submissions` | Agent returns submission history with claim/job references |
| `test_submission_with_invalid_claim_handled` | Malformed claim payload produces a meaningful response rather than a crash |

### B2BI workflow tests (`tests/integration/test_b2bi_workflow.py`)

End-to-end tests covering the full B2B Data Interchange pipeline — bucket access, transformer invocation, and acknowledgment retrieval.

## Running tests

```bash
# Integration tests (requires deployed stack)
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/runtime/test_agent_runtimes.py::TestClaimsSubmissionAgent -v

# B2BI workflow tests
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/test_b2bi_workflow.py -v
```
