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
- **AgentCore Gateway** — for HealthLake tools (FHIR R4 patient clinical data + a create-only `create_fhir_resource` write tool backed by the AWS Labs HealthLake MCP server), payor policy tools (policy search, dynamic prior auth requirement assessment), and CDS Hooks tools (EHR integration)

## Entry points
This skill is reached three ways, all of which converge on the same agent:
- **CDS Hooks (EHR / sandbox)** — the public CDS Hooks REST endpoint (`GET /cds-services`, `POST /cds-services/prior-auth-order-select`) fires on order entry. The `order-select` card deep-links to the Amplify UI carrying `patientId`, `code`, `desc`, and `payor`.
- **Amplify UI** — `/orders/prior-auth` (launched from the card or from a created order). Patient name, payer, member ID, and conditions auto-populate from HealthLake via the deterministic `/patients` API; the agent then runs the workflow.
- **Direct chat** — invoke the agent with a free-text prior-auth request.

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
- Input: `procedure_code` (CPT/HCPCS), `payor_name`, and `description` (the ordered drug/procedure text)
- The determination is **dynamic and model-assessed for the actual submitted order** (drug class, cost, advanced imaging, surgery), grounded in payer policy when a knowledge base is configured — there is no hardcoded drug allow-list. Medications often arrive as RxNorm codes, so the `description` is the reliable signal.
- Output: whether prior auth is required, documentation requirements

This same rule is the single source of truth shared with the CDS Hooks `order-select` card.

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

### Step 8: Persist the decision (USER-INITIATED only)
The agent only *recommends*. Persisting the authorization to the patient's
record is an explicit human action — the provider clicks **Save Authorization**
in the UI, which writes the `ClaimResponse` via a Cognito-authorized,
create-only endpoint (`POST /authorizations`). Do **not** auto-write the
decision to HealthLake as part of the agent workflow. The Gateway
`create_fhir_resource` tool exists for create-only writes (ClaimResponse/Task)
but should only be used when explicitly directed.

## Key Conventions
- Prior-auth requirement is **dynamic / model-assessed for the submitted order** — never a hardcoded drug or code list
- Persistence to HealthLake is **user-initiated**, never automatic — the agent recommends; a human saves
- Writes are **create-only** (ClaimResponse/Task); update/delete are not exposed
- Always retrieve actual patient data from HealthLake — never fabricate clinical evidence
- Always check payor-specific policies before making determinations
- Low temperature (0.1) for clinical accuracy — avoid hallucinated clinical details
- Input sanitization is applied to all user prompts (defense against prompt injection)
- Bedrock Guardrails enforce: prompt attack filtering, healthcare denied topics, PII output filtering for HIPAA identifiers
- If clinical data is insufficient, clearly state what additional information is needed rather than proceeding with incomplete evidence
- FHIR resources follow Da Vinci PAS Implementation Guide profiles
- Priority levels: normal (routine), urgent (expedited review needed), emergency (immediate)
