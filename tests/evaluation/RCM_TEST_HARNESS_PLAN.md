# RCM Agent Test Harness — Implementation Plan

## Overview

Extend the existing Langfuse evaluation framework (built for `hospital-safety-agent`) to cover all 6 RCM agents. The framework already has the scaffolding — we need golden sets, judge prompts, score configs, and deployment gates for each agent.

## Current State (What Exists)

- [x] `tests/evaluation/run_experiment.py` — generic experiment runner (supports `--agent` flag)
- [x] `tests/evaluation/judge_prompt.py` — judge prompt uploader (hospital-safety only)
- [x] `tests/evaluation/setup_langfuse.py` — score config creator (shared + hospital-safety)
- [x] `tests/evaluation/check_gates.py` — deployment gate checker (hospital-safety only)
- [x] `tests/evaluation/golden_sets/hospital_safety.py` — 20 curated incidents
- [x] `tests/evaluation/upload_golden_sets.py` — dataset uploader (hospital-safety only)
- [x] Unit tests for claims assembly (EDI 837P), appeals (letter builder), prior auth (bundle, status, response)
- [x] Integration tests for claims submission, claims assembly, medical coding, B2B workflow

## What We're Building

### Phase 1: Golden Sets (6 files) ← START HERE
Create curated test cases with expected outputs for each RCM agent.

| # | File | Agent | Cases | Status |
|---|---|---|---|---|
| 1.1 | `golden_sets/prior_authorization.py` | prior-authorization-agent | 15 | ✅ |
| 1.2 | `golden_sets/eligibility_verification.py` | eligibility-verification-agent | 10 | ✅ |
| 1.3 | `golden_sets/medical_coding.py` | medical-coding-agent | 18 | ✅ |
| 1.4 | `golden_sets/claims_assembly.py` | claims-assembly-agent | 12 | ✅ |
| 1.5 | `golden_sets/claims_submission.py` | claims-submission-agent | 7 | ✅ |
| 1.6 | `golden_sets/appeals.py` | appeals-agent | 10 | ✅ |

### Phase 2: Judge Prompts + Score Configs (modify 2 existing files)
Add agent-specific scoring rubrics and Langfuse score configurations.

| # | Task | File | Status |
|---|---|---|---|
| 2.1 | Add RCM judge prompts (system + user) | `judge_prompt.py` → make multi-agent | ✅ All 7 agents |
| 2.2 | Add RCM score configs to `AGENT_SCORE_CONFIGS` | `setup_langfuse.py` | ✅ All 6 agents |

### Phase 3: Wire Into Experiment Runner (modify 2 existing files)
Register agents in the dataset map and add agent-specific scoring logic.

| # | Task | File | Status |
|---|---|---|---|
| 3.1 | Add all 6 agents to `AGENT_DATASET_MAP` | `run_experiment.py` | ✅ |
| 3.2 | Make `record_scores()` agent-aware | `run_experiment.py` | ✅ |
| 3.3 | Add `upload_golden_sets.py` support for all agents | `upload_golden_sets.py` | ✅ All 7 agents registered |

### Phase 4: Deployment Gates (modify 1 existing file)
Define pass/fail thresholds per agent.

| # | Task | File | Status |
|---|---|---|---|
| 4.1 | Add gate configs for all 6 agents to `AGENT_GATES` | `check_gates.py` | ✅ All 6 agents |

### Phase 5: End-to-End Workflow Test (1 new file)
Chain all agents in sequence for a single patient.

| # | Task | File | Status |
|---|---|---|---|
| 5.1 | Create E2E workflow test | `tests/evaluation/run_e2e_workflow.py` | ✅ |

### Phase 6: CI/CD Integration
Wire into pipeline.

| # | Task | Status |
|---|---|---|
| 6.1 | Add eval step to CI/CD (run_experiment → check_gates) | ✅ buildspec-eval.yml created |
| 6.2 | Create annotation queues per agent in Langfuse UI | ✅ Instructions in plan |

---

## Detailed Specs Per Agent

### 1.1 Prior Authorization Agent (`pa__` prefix)

**Golden set structure:**
```python
{
    "id": "pa_001",
    "category": "requires_auth",
    "input": {
        "patient_id": "Patient/123",
        "procedure_code": "72148",  # MRI lumbar spine
        "procedure_description": "MRI lumbar spine without contrast",
        "payor": "UnitedHealthcare",
        "clinical_context": "Patient with chronic low back pain, failed 6 weeks PT..."
    },
    "expected_output": {
        "auth_required": True,
        "medical_necessity_met": True,
        "clinical_data_gathered": ["conditions", "medications", "observations"],
        "payor_policy_cited": True,
        "fhir_bundle_valid": True,
        "key_findings": ["chronic low back pain", "failed conservative therapy"],
        "must_not_contain": []
    }
}
```

**Agent-specific scores:**
- `pa__auth_determination_accuracy` (bool) — correct yes/no on auth required
- `pa__medical_necessity_accuracy` (bool) — correct met/not met
- `pa__clinical_data_completeness` (1-5) — all relevant data gathered from HealthLake
- `pa__fhir_bundle_validity` (bool) — valid FHIR Claim bundle structure
- `pa__payor_policy_citation` (bool) — cited relevant policy, not hallucinated

**Deployment gates:**
- `pa__auth_determination_accuracy` rate_true >= 0.95
- `mean(clinical_accuracy)` >= 4.0
- `mean(pa__clinical_data_completeness)` >= 3.5
- `overall_pass` rate_true >= 0.90

**Test case categories (15-20 total):**
- 5 procedures requiring auth (MRI, CT, surgery, DME, specialty drugs)
- 3 procedures NOT requiring auth (routine labs, preventive care, ER)
- 3 cases with insufficient clinical evidence (auth required but necessity not met)
- 2 payor-specific edge cases (different payors, different rules for same CPT)
- 2 cases with complex clinical history (multiple comorbidities)

---

### 1.2 Eligibility Verification Agent (`ev__` prefix)

**Golden set structure:**
```python
{
    "id": "ev_001",
    "category": "active_coverage",
    "input": {
        "patient_id": "Patient/456",
        "service_type": "MRI",
        "date_of_service": "2026-04-15"
    },
    "expected_output": {
        "coverage_active": True,
        "plan_type": "PPO",
        "effective_dates": {"start": "2026-01-01", "end": "2026-12-31"},
        "copay": 50,
        "coinsurance": 0.20,
        "deductible_met": False,
        "deductible_remaining": 1500,
        "prior_auth_required": True,
        "key_findings": ["active PPO coverage", "deductible not met"],
        "must_not_contain": []
    }
}
```

**Agent-specific scores:**
- `ev__coverage_status_accuracy` (bool) — correct active/inactive/expired
- `ev__benefit_detail_accuracy` (1-5) — copay, coinsurance, deductible correct
- `ev__auth_flag_accuracy` (bool) — correct prior auth required determination

**Test case categories (10-15 total):**
- 4 active coverage (different plan types: HMO, PPO, HDHP, Medicare)
- 3 expired/terminated coverage
- 2 coverage with exclusions for requested service
- 2 Medicaid/Medicare edge cases
- 2 coordination of benefits (dual coverage)

---

### 1.3 Medical Coding Agent (`mc__` prefix)

**Golden set structure:**
```python
{
    "id": "mc_001",
    "category": "single_diagnosis",
    "input": {
        "clinical_text": "Patient presents with acute exacerbation of chronic obstructive pulmonary disease. Chest X-ray shows hyperinflation. Started on prednisone taper and albuterol nebulizer.",
    },
    "expected_output": {
        "icd10_codes": [{"code": "J44.1", "description": "COPD with acute exacerbation"}],
        "cpt_codes": [{"code": "71046", "description": "Chest X-ray 2 views"}],
        "snomed_codes": [{"code": "195951007", "description": "Acute exacerbation of COPD"}],
        "entities_extracted": ["COPD", "prednisone", "albuterol", "chest X-ray"],
        "key_findings": ["J44.1", "acute exacerbation"],
        "must_not_contain": []
    }
}
```

**Agent-specific scores:**
- `mc__icd10_accuracy` (1-5) — correct codes at highest specificity
- `mc__cpt_accuracy` (1-5) — correct procedure codes
- `mc__entity_extraction_recall` (1-5) — all medical entities found
- `mc__code_specificity` (bool) — used most specific code, not parent

**Test case categories (20-25 total):**
- 5 single diagnosis (clear-cut coding)
- 5 multi-diagnosis (comorbidities, multiple conditions)
- 3 procedure-heavy notes (surgical, imaging, lab)
- 3 medication-focused (drug interactions, adverse reactions)
- 3 ambiguous notes (requires clinical judgment on code selection)
- 3 edge cases (unspecified laterality, rule-out diagnoses, history-of)

---

### 1.4 Claims Assembly Agent (`ca__` prefix)

**Golden set structure:**
```python
{
    "id": "ca_001",
    "category": "complete_claim",
    "input": {
        "patient_id": "Patient/789",
        "provider_npi": "1234567890",
        "provider_tax_id": "12-3456789",
        "diagnosis_codes": ["J44.1"],
        "procedure_code": "99213",
        "date_of_service": "2026-04-15",
        "charge_amount": 150.00,
        "payor_id": "UHC001"
    },
    "expected_output": {
        "edi_837p_valid": True,
        "hipaa_5010_compliant": True,
        "all_required_fields_present": True,
        "missing_fields": [],
        "validation_errors": [],
        "key_findings": ["valid NPI", "valid Tax ID", "valid ICD-10"],
        "must_not_contain": []
    }
}
```

**Agent-specific scores:**
- `ca__edi_structural_validity` (bool) — valid EDI 837P structure
- `ca__hipaa_compliance` (bool) — passes HIPAA 5010 validation
- `ca__field_completeness` (1-5) — all required fields present and formatted
- `ca__payer_rule_adherence` (bool) — payer-specific rules followed

**Test case categories (10-15 total):**
- 4 complete valid claims (different service types)
- 3 claims with missing required fields (should flag errors)
- 3 payer-specific rule violations (should catch)
- 2 HIPAA format edge cases (date formats, code set versions)
- 2 multi-line claims (multiple procedures)

---

### 1.5 Claims Submission Agent (`cs__` prefix)

**Golden set structure:**
```python
{
    "id": "cs_001",
    "category": "successful_submission",
    "input": {
        "claim_json": { ... },  # assembled EDI 837P
        "payor_id": "UHC001"
    },
    "expected_output": {
        "submission_successful": True,
        "transformation_job_status": "COMPLETED",
        "acknowledgment_type": "997",
        "acknowledgment_status": "accepted",
        "key_findings": ["submitted via B2B", "997 accepted"],
        "must_not_contain": []
    }
}
```

**Agent-specific scores:**
- `cs__submission_accuracy` (bool) — correct B2B invocation
- `cs__acknowledgment_parsing` (bool) — 997/999 correctly interpreted
- `cs__status_tracking` (bool) — transformation job status correctly reported

**Test case categories (5-10 total):**
- 3 successful submissions with 997 accepted
- 2 submissions with 999 rejection (should report errors)
- 2 transformation job failures (should handle gracefully)
- 1 timeout/retry scenario

---

### 1.6 Appeals Agent (`ap__` prefix)

**Golden set structure:**
```python
{
    "id": "ap_001",
    "category": "medical_necessity_denial",
    "input": {
        "claim_id": "CLM-001",
        "denial_reason_code": "CO-50",  # Medical necessity
        "denial_description": "Service not medically necessary",
        "procedure_code": "72148",
        "diagnosis_codes": ["M54.5"],
        "payor": "UnitedHealthcare",
        "date_of_denial": "2026-04-01"
    },
    "expected_output": {
        "denial_code_identified": True,
        "carc_rarc_lookup_correct": True,
        "filing_deadline_correct": True,
        "filing_deadline_days": 180,
        "appeal_letter_generated": True,
        "clinical_evidence_cited": True,
        "letter_saved_to_s3": True,
        "key_findings": ["CO-50", "medical necessity", "180 days"],
        "must_not_contain": []
    }
}
```

**Agent-specific scores:**
- `ap__denial_code_accuracy` (bool) — correct CARC/RARC lookup
- `ap__deadline_accuracy` (bool) — correct filing deadline calculated
- `ap__letter_completeness` (1-5) — all required sections present
- `ap__clinical_evidence_citation` (bool) — relevant clinical evidence included
- `ap__regulatory_compliance` (bool) — follows payer-specific appeal rules

**Test case categories (10-15 total):**
- 3 medical necessity denials (different procedures)
- 2 authorization-related denials (no prior auth obtained)
- 2 coding-related denials (incorrect codes)
- 2 timely filing denials (deadline edge cases)
- 2 duplicate claim denials
- 2 coordination of benefits denials

---

## File Changes Summary

| File | Change Type | Description |
|---|---|---|
| `golden_sets/prior_authorization.py` | NEW | 15-20 prior auth test cases |
| `golden_sets/eligibility_verification.py` | NEW | 10-15 eligibility test cases |
| `golden_sets/medical_coding.py` | NEW | 20-25 medical coding test cases |
| `golden_sets/claims_assembly.py` | NEW | 10-15 claims assembly test cases |
| `golden_sets/claims_submission.py` | NEW | 5-10 claims submission test cases |
| `golden_sets/appeals.py` | NEW | 10-15 appeals test cases |
| `judge_prompt.py` | MODIFY | Add per-agent judge prompts (system + user templates) |
| `setup_langfuse.py` | MODIFY | Add score configs for all 6 agents |
| `run_experiment.py` | MODIFY | Add agents to dataset map, make scoring agent-aware |
| `upload_golden_sets.py` | MODIFY | Support uploading all agent golden sets |
| `check_gates.py` | MODIFY | Add deployment gates for all 6 agents |
| `run_e2e_workflow.py` | NEW | End-to-end chained workflow test |
| `README.md` | MODIFY | Document all agents in eval pipeline |

---

## Execution Order

Start with **prior-authorization-agent** (most complex, highest customer value) then cascade:

1. `prior_authorization.py` golden set → judge prompt → score configs → gates
2. `medical_coding.py` (second most complex, Comprehend Medical dependency)
3. `claims_assembly.py` (EDI validation is deterministic — easier to validate)
4. `eligibility_verification.py`
5. `appeals.py`
6. `claims_submission.py` (simplest — mostly B2B integration)
7. `run_e2e_workflow.py` (requires all above)

---

## Dependencies & Blockers

| Dependency | Owner | Notes |
|---|---|---|
| Clinical SME review of golden sets | TBD | Expected outputs must be clinically validated |
| Deployed stack with HealthLake data | Infra | Integration tests need sample FHIR patients |
| Langfuse instance access | DevOps | Score configs + annotation queues |
| Sample payor policy documents | Domain | Prior auth agent needs KB populated |
| Sample medical codes KB | Domain | Medical coding agent needs ICD-10/CPT/SNOMED data |
| Sample denial codes KB | Domain | Appeals agent needs CARC/RARC data |

---

## How to Resume

If we stop partway through, pick up from the first unchecked `☐` in the Phase table above.
Each phase is independently runnable — you can test a single agent's golden set + judge + gates
without completing all 6.

To test a single agent after completing its phase 1-4 tasks:
```bash
# Upload golden set
uv run python3 tests/evaluation/upload_golden_sets.py --agent prior-authorization-agent

# Create score configs
uv run python3 tests/evaluation/setup_langfuse.py --agent prior-authorization-agent

# Upload judge prompt
uv run python3 tests/evaluation/judge_prompt.py --agent prior-authorization-agent --promote

# Run experiment
uv run python3 tests/evaluation/run_experiment.py --agent prior-authorization-agent --dry-run

# Check gates
uv run python3 tests/evaluation/check_gates.py --agent prior-authorization-agent --run-name <run-name>
```
