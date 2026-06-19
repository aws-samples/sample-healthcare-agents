# Medical Coding Agent

Extracts standardized medical codes from clinical text using Amazon Comprehend Medical for entity recognition and a Bedrock Knowledge Base for code lookup.

## What it does

Given free-text clinical notes, the agent:

1. Calls **Comprehend Medical** (`extract_medical_entities`) to identify conditions, medications, procedures, and anatomy
2. Searches the **medical codes knowledge base** (`search_medical_codes`) for ICD-10-CM, CPT, and SNOMED CT codes matching each entity
3. Returns codes with descriptions and usage guidance, considering clinical context (e.g. rule-out vs confirmed diagnosis, laterality, procedure type)
4. Optionally detects **PHI** (`detect_phi`) in clinical text

## Example prompts

```
Extract diagnosis codes from: Patient presents with acute exacerbation of COPD.
Started on prednisone taper and albuterol nebulizer.
```
→ Returns J44.1 (COPD with acute exacerbation)

```
What CPT code for a colonoscopy with snare polypectomy of an 8mm sessile sigmoid polyp?
```
→ Returns 45385

```
Perform complete medical coding for: 65-year-old with type 2 diabetes and CKD stage 3, eGFR 45.
```
→ Returns E11.22 (T2DM with CKD) + N18.3 (CKD stage 3)

```
Detect PHI in: Patient John Doe, DOB 01/15/1980, MRN 987654.
```
→ Flags name, date of birth, and MRN as protected health information

## Supported code types

| Type | System | Use |
|---|---|---|
| ICD-10-CM | Diagnoses | Conditions, symptoms, history, screening |
| CPT | Procedures | Office visits, surgery, imaging, labs |
| SNOMED CT | Clinical terms | Interoperability, terminology mapping |

## Key coding rules the agent applies

- **Rule-out / unconfirmed** diagnoses → symptom code (e.g. R07.9 chest pain), not definitive (e.g. not I21 MI)
- **History vs active** → Z85 personal history codes for surveillance visits, not active C-codes
- **Laterality** → right vs left specific codes (M17.11 right knee OA, not M17.12 left)
- **Combination codes** → E11.22 covers both T2DM and CKD together; N18.3 added separately for stage
- **Adverse effects** → T-codes for drug reactions (not poisoning codes unless intentional)

## Knowledge Base Data

The medical codes knowledge base is pre-loaded with **sample reference data** for demonstration purposes, covering a subset of ICD-10-CM, CPT, and SNOMED CT codes.

> **Important:** This is sample data only. Customers deploying this agent should replace the contents of the medical codes KB S3 bucket with licensed, current-year code sets from the appropriate authorities (CMS for ICD-10-CM, AMA for CPT, SNOMED International for SNOMED CT) before using in production.

## Tests

### Unit tests (`tests/unit/patterns/medical_coding/`)

| Test | What it validates |
|---|---|
| `TestGetSsmParameter` (3 tests) | SSM lookup happy path; `ParameterNotFound` raises `ValueError`; generic exceptions wrapped correctly |
| `TestGetSystemPrompt` (2 tests) | Returns correct prompt text; ARN parsed to extract promptId and version correctly |
| `TestQueryKnowledgeBase` (4 tests) | Results formatted from raw Bedrock response; empty results return `[]`; exceptions return `[]` gracefully; `max_results` passed through to API |
| `TestKbTool` (4 tests) | No-results returns JSON message; results include content + relevance score; `code_type=all` passes query unchanged; specific code type appended to query string |
| `agent_stream` (5 tests) | Missing `prompt`/`userId`/`sessionId` each yield an error event; agent creation failure yields error event; happy-path events forwarded unchanged |

### Integration tests (`tests/integration/runtime/TestMedicalCodingAgent`)

| Test | What it validates |
|---|---|
| `test_extracts_entities_from_clinical_note` | Comprehend Medical returns conditions and medications from free text |
| `test_detects_phi_in_note` | PHI detection flags name, DOB, MRN, or address |
| `test_single_diagnosis_icd10` | J44.1 returned for COPD with acute exacerbation |
| `test_multi_diagnosis_icd10` | ≥3 of J18/I50/I48/E11 returned for complex multi-comorbidity admit note |
| `test_diabetes_with_ckd_icd10` | E11.22 + N18.3 both present for T2DM+CKD combination |
| `test_medication_adverse_effect_icd10` | T36 or T78 codes returned for penicillin anaphylaxis |
| `test_ambiguous_note_uses_symptom_code` | R07 (chest pain) returned for rule-out ACS; I21 (MI) not returned |
| `test_history_vs_active_cancer_code` | Z85 history code returned for surveillance visit; active C50 not returned |
| `test_procedure_cpt_code` | 47562 returned for laparoscopic cholecystectomy with cholangiogram |
| `test_colonoscopy_with_polypectomy_cpt` | 45385 returned for colonoscopy with snare polypectomy |
| `test_office_visit_cpt` | 99214 returned for moderate complexity established patient visit |
| `test_snomed_mapping` | SNOMED CT concept returned for a clinical term |
| `test_full_coding_workflow` | M17.11 + 27447 both returned for right total knee arthroplasty note |
| `test_rejects_wrong_laterality` | M17.11 (right) returned; M17.12 (left) not returned |

## Running tests

```bash
# Unit tests (no AWS required)
python -m pytest tests/unit/patterns/medical_coding/ -v

# Integration tests (requires deployed stack)
STACK_NAME=<your-stack> AWS_DEFAULT_REGION=us-east-1 \
  python -m pytest tests/integration/runtime/test_agent_runtimes.py::TestMedicalCodingAgent -v
```
