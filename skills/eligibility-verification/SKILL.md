---
name: eligibility-verification
description: Use when a provider needs to verify patient insurance eligibility, check active coverage status, determine benefits and cost sharing (copay, coinsurance, deductible), or assess whether a service requires prior authorization.
---

# Eligibility Verification

## When to use this skill
- Verify if a patient has active insurance coverage
- Check coverage effective dates and plan details
- Determine benefits for a specific procedure or service
- Calculate patient cost sharing (copay, coinsurance, deductible)
- Determine if prior authorization is required for a service
- Retrieve patient demographics from HealthLake

## MCP Servers Used
- **AgentCore Gateway** — for HealthLake tools (FHIR R4 patient data, coverage, and clinical records)

## Workflow: Verify Patient Eligibility

### Step 1: Patient identification
Tools via Gateway:
- `advanced_patient_search` — search by demographics (name, DOB, member ID)
- `get_patient_everything` — comprehensive patient record retrieval

Verify:
- Patient identity matches request (name, date of birth, member ID)
- Correct patient record is selected (avoid wrong-patient errors)

### Step 2: Coverage verification
Retrieve from HealthLake Coverage resources:
- Insurance plan name and type (commercial, Medicare, Medicaid, Tricare)
- Payor organization name and ID
- Group number and subscriber ID
- Coverage effective dates (start and end)
- Coverage status (active, cancelled, entered-in-error)

> Deterministic auto-populate: the app's `/patients?q=<id>` API resolves
> demographics **and** active Coverage (payer + member ID) and conditions in a
> single fast FHIR call. Prefer this for pre-filling intake fields rather than
> asking the model to parse free text. The agent is still the source of truth
> for the eligibility *assessment*.

Decision: If coverage is NOT active → stop and report to provider with recommended next steps.

### Step 3: Benefits check
Determine for the requested service:
- Is the service a covered benefit under the plan?
- Are there benefit limitations or exclusions?
- Remaining benefit amounts (visit limits, dollar caps)
- Network status of the requesting provider (in-network vs out-of-network)

### Step 4: Cost sharing details
Calculate patient financial responsibility:
- **Copay**: fixed amount per visit/service
- **Coinsurance**: percentage patient pays after deductible
- **Deductible**: amount met vs remaining for the year
- **Out-of-pocket maximum**: amount met vs remaining
- Estimated total patient responsibility for the service

### Step 5: Prior authorization determination
Check:
- Does this service/procedure require prior authorization?
- Is there an existing prior auth on file for this service?
- What are the prior auth requirements if needed?
- Recommend proceeding with prior auth workflow if required

### Step 6: Summary and next steps
Present structured eligibility verification:
- Coverage status (active/inactive, plan type, dates)
- Benefits determination (covered/excluded/limited)
- Cost sharing breakdown
- Prior auth requirement (yes/no, requirements if yes)
- Clear recommendation: proceed, obtain prior auth, or contact payor

## Tool Reference

| Tool | Use Case | Key Parameters |
|------|----------|----------------|
| `get_patient_conditions` | Diagnoses and conditions | patient_id |
| `get_patient_medications` | Current medications | patient_id |
| `get_patient_observations` | Lab results, vitals | patient_id |
| `get_patient_allergies` | Allergy records | patient_id |
| `get_patient_appointments` | Scheduled/past visits | patient_id |
| `get_patient_everything` | Full patient record | patient_id |
| `advanced_patient_search` | Find patient by demographics | name, dob, member_id |

## Key Conventions
- Always retrieve actual patient data from HealthLake — never assume coverage status
- Clearly distinguish between verified data and estimated information
- If coverage data is unavailable in HealthLake, recommend a real-time 270/271 eligibility transaction with the payor
- Follow HIPAA guidelines — minimize PHI exposure in responses
- Coverage status can change daily — verification is point-in-time
- Some plans have separate deductibles for in-network vs out-of-network
