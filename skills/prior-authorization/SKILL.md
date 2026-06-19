---
name: prior-authorization
description: Use when a provider needs to submit a prior authorization request, check if a procedure requires prior auth, gather clinical evidence from HealthLake, assess medical necessity against payor criteria, or generate FHIR Da Vinci PAS Bundles and ClaimResponses.
---

# Prior Authorization

## When to use this skill
- Determine if a procedure requires prior authorization for a given payor
- Gather clinical evidence to support medical necessity
- Search payor policy documents for coverage criteria
- Assemble a prior authorization request with supporting documentation
- Generate FHIR PAS Bundle (Claim + referenced resources)
- Generate FHIR ClaimResponse for authorization decisions
- Handle CDS Hooks triggers from EHR order placement

## MCP Servers Used
- **AgentCore Gateway** — for HealthLake tools (FHIR R4 patient clinical data), payor policy tools (policy search, prior auth requirements lookup), and CDS Hooks tools (EHR integration)

## Workflow: Process Prior Authorization Request

### Step 1: Order detection and initiation
Identify:
- Requested procedure/service and its CPT/HCPCS code
- Patient identifier and insurance payor
- Ordering provider and rendering provider (if different)
- Clinical indication (primary diagnosis)

CDS Hooks integration (if triggered from EHR):
- Tool: `handle_order_select` — processes order-select hook from EHR
- Automatically identifies procedure and patient context

### Step 2: Check prior auth requirement
Tool (via Gateway): `lookup_prior_auth_requirements`
- Input: procedure code (CPT/HCPCS), payer_id
- Output: whether prior auth is required, documentation requirements

Decision: If prior auth is NOT required → inform provider and stop.

### Step 3: Gather clinical evidence from HealthLake
Tools via Gateway:
| Tool | Data Retrieved |
|------|---------------|
| `get_patient_conditions` | Diagnoses (ICD-10) supporting medical necessity |
| `get_patient_medications` | Current/historical medications (conservative treatment evidence) |
| `get_patient_observations` | Lab results, imaging, vitals |
| `get_patient_allergies` | Allergy/intolerance records |
| `get_patient_everything` | Comprehensive patient record |

Collect:
- Primary diagnosis supporting the procedure
- Failed conservative treatments (medications, physical therapy, etc.)
- Relevant lab values and imaging results
- Duration of symptoms / condition progression

### Step 4: Review payor policy criteria
Tool (via Gateway): `search_payor_policies`
- Input: query describing procedure and clinical scenario
- Output: coverage criteria, medical necessity requirements, required documentation

Check:
- Does clinical evidence meet the payor's specific criteria?
- Are all required documentation items available?
- Has the payor's conservative treatment requirement been satisfied?

### Step 5: Assemble FHIR PAS Bundle
Tool: `build_pas_claim_bundle`
- Input:
  - patient: FHIR Patient resource from HealthLake
  - practitioner: FHIR Practitioner resource
  - coverage: FHIR Coverage resource
  - insurer: FHIR Organization (the payer)
  - service_items_data: list of {product_or_service: {system, code, display}, diagnosis_link_ids, quantity, unit_price}
  - supporting_info: list of FHIR resources (Condition, MedicationRequest, Observation)
  - priority: "normal" | "urgent" | "emergency"
  - questionnaire_response: optional FHIR QuestionnaireResponse
- Output: {claim, bundle, validation_issues}

If validation issues exist → report to provider before proceeding.

### Step 6: Generate authorization decision
Tool: `generate_claim_response`
- Input:
  - claim_reference: "Claim/{id}"
  - patient_reference: "Patient/{id}"
  - insurer_reference: "Organization/{id}"
  - decision: "approved" | "denied" | "pended"
  - disposition: human-readable rationale
  - pre_auth_ref: authorization number (for approved; auto-generated if omitted)
  - error_code: X12 adjustment reason code (for denied)
  - review_action: review action code (for pended)
- Output: FHIR ClaimResponse resource

### Step 7: Present results and next steps
Structured response sections:
1. **Eligibility & Coverage** — insurance status and plan details
2. **Clinical Evidence** — gathered conditions, medications, labs
3. **Payor Policy Requirements** — what the payor requires and whether met
4. **Medical Necessity Assessment** — clinical evidence vs criteria analysis
5. **Authorization Decision** — recommended/denied/additional documentation needed
6. **Next Steps** — concrete provider actions
7. **FHIR Resources Generated** — PAS Bundle summary and ClaimResponse

## Key Conventions
- Always retrieve actual patient data from HealthLake — never fabricate clinical evidence
- Always check payor-specific policies before making determinations
- Low temperature (0.1) for clinical accuracy — avoid hallucinated clinical details
- Input sanitization is applied to all user prompts (defense against prompt injection)
- Bedrock Guardrails enforce: prompt attack filtering, healthcare denied topics, PII output filtering for HIPAA identifiers
- If clinical data is insufficient, clearly state what additional information is needed rather than proceeding with incomplete evidence
- FHIR resources follow Da Vinci PAS Implementation Guide profiles
- Priority levels: normal (routine), urgent (expedited review needed), emergency (immediate)
