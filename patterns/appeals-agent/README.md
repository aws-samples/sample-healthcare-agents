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

## Tests

### Unit tests (`tests/unit/patterns/appeals_agent/`)

| Test | What it validates |
|---|---|
| `test_appeal_letter_builder.py` | `validate_components` catches missing/invalid fields; `build_appeal_letter_html` produces well-formed HTML with all sections; `validate_and_build` end-to-end pipeline |
| Deadline tracker tests | `check_filing_deadline` returns correct status for on-time, near-deadline, and expired windows; payer-specific deadlines applied correctly |

### Integration tests (`tests/integration/runtime/TestAppealsAgent`)

| Test | What it validates |
|---|---|
| `test_analyze_carc_denial` | CARC 50 denial analyzed; response includes appeal/medical necessity/clinical guidance |
| `test_lookup_appeal_filing_deadline` | Payer-specific deadline returned with day count or date |
| `test_generate_appeal_letter_medical_necessity` | Complete letter generated (>300 chars) with appeal/denial/clinical content |
| `test_generate_appeal_letter_timely_filing` | CO-29 timely filing denial → appeal letter with proof-of-submission language |
| `test_search_clinical_guidelines` | Clinical criteria for MRI lumbar spine retrieved from KB |
| `test_multiple_denial_codes_analysis` | CO-4 + CO-97 dual denial analyzed with separate strategies |
| `test_appeal_letter_saved_to_s3` | Letter generated and saved; response contains S3/URL/saved confirmation |

### Knowledge base tests (`tests/integration/test_appeals_agent.py`)

Direct Bedrock KB retrieval tests for denial codes, appeal regulations, and clinical guidelines, plus S3 round-trip tests for letter storage and presigned URL generation.

## Running tests

```bash
# Unit tests (no AWS required)
python -m pytest tests/unit/patterns/appeals_agent/ -v

# Integration tests (requires deployed stack)
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/runtime/test_agent_runtimes.py::TestAppealsAgent -v

# KB + S3 storage tests
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/test_appeals_agent.py -v
```
