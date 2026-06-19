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

## Tests

### Integration tests (`tests/integration/runtime/TestClaimsAssemblyAgent`)

| Test | What it validates |
|---|---|
| `test_validate_complete_claim` | All required fields present → agent reports validation pass |
| `test_assemble_edi_837p_structure` | Complete inputs → EDI 837P segments (CLM, NM1, SV1, DTP, or 837) appear in response |
| `test_rejects_invalid_npi` | 5-digit NPI → agent flags the format error |
| `test_rejects_missing_diagnosis` | No diagnosis code → agent flags missing required field |
| `test_hipaa_5010_compliance_check` | Agent references HIPAA 5010 standards in compliance response |
| `test_multi_service_line_claim` | Both procedure codes (99214 + 93000) appear in assembled claim |
| `test_payer_specific_validation_rules` | Medicare-specific requirements retrieved from validation KB |
| `test_procedure_code_format_validation` | 4-digit CPT → agent flags the format error |

## Running tests

```bash
# Integration tests (requires deployed stack)
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/runtime/test_agent_runtimes.py::TestClaimsAssemblyAgent -v

# KB retrieval tests (requires deployed stack)
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/test_claims_assembly_agent.py -v
```
