# Claim Adjustment Reason Codes (CARC) and Remittance Advice Remark Codes (RARC)
# Reference for Appeals Agent — Denial Analysis and Appeal Strategy

## CARC Codes — Common Denial Reasons

### Coverage and Eligibility Denials

CARC 1 — Deductible Amount
- Description: Amount applied to patient deductible
- Appeal Strategy: Verify deductible accumulation; request updated accumulators from payer
- Required Evidence: Explanation of Benefits showing prior payments, deductible tracking

CARC 2 — Coinsurance Amount
- Description: Amount applied to patient coinsurance
- Appeal Strategy: Verify plan coinsurance percentage; check if service is in-network
- Required Evidence: Plan benefit summary, provider network status

CARC 3 — Co-payment Amount
- Description: Amount applied to patient copay
- Appeal Strategy: Verify copay tier; confirm service category classification
- Required Evidence: Plan benefit summary, service classification documentation

CARC 4 — The procedure code is inconsistent with the modifier used
- Description: Modifier does not match procedure
- Appeal Strategy: Correct modifier and resubmit; provide documentation of medical necessity for modifier
- Required Evidence: Operative report, clinical notes supporting modifier use

CARC 16 — Claim/service lacks information needed for adjudication
- Description: Missing or invalid information on claim
- Appeal Strategy: Identify missing fields from ERA/835; resubmit with complete information
- Required Evidence: Corrected claim form with all required fields

CARC 18 — Exact duplicate claim/service
- Description: Duplicate claim submission detected
- Appeal Strategy: If not a true duplicate, submit with documentation showing distinct services
- Required Evidence: Medical records showing separate encounters, distinct dates/times of service

CARC 26 — Expenses incurred prior to coverage
- Description: Service date before coverage effective date
- Appeal Strategy: Verify coverage effective date; request retroactive eligibility if applicable
- Required Evidence: Enrollment confirmation, coverage effective date documentation

CARC 27 — Expenses incurred after coverage terminated
- Description: Service date after coverage end date
- Appeal Strategy: Verify termination date; check COBRA or continuation coverage eligibility
- Required Evidence: Coverage termination notice, COBRA election documentation

### Medical Necessity Denials

CARC 50 — Non-covered service because not deemed a medical necessity
- Description: Payer determined service is not medically necessary
- Appeal Strategy: Submit peer-reviewed literature, clinical guidelines, and detailed clinical notes
- Required Evidence: Clinical notes, lab results, imaging reports, peer-reviewed studies, letter of medical necessity from treating physician
- Escalation: Request peer-to-peer review with payer medical director

CARC 96 — Non-covered charge(s)
- Description: Service not covered under patient benefit plan
- Appeal Strategy: Review plan documents for coverage; check for alternative benefit categories
- Required Evidence: Plan benefit summary, clinical documentation supporting medical necessity

CARC 97 — Payment adjusted because the benefit for this service is included in the payment for another service
- Description: Service bundled with another procedure
- Appeal Strategy: Submit modifier 59 or XE/XS/XP/XU with documentation of distinct service
- Required Evidence: Operative report showing separate procedure, distinct anatomical site documentation

### Prior Authorization Denials

CARC 197 — Precertification/authorization/notification absent
- Description: Required prior authorization was not obtained
- Appeal Strategy: Submit retroactive authorization request; provide documentation of emergency/urgent circumstances
- Required Evidence: Authorization number if obtained, clinical notes showing urgency, emergency department records

CARC 198 — Precertification/authorization/notification exceeded
- Description: Service exceeded authorized quantity or scope
- Appeal Strategy: Request authorization extension; document medical necessity for additional services
- Required Evidence: Original authorization, clinical notes supporting additional services, updated treatment plan

CARC 199 — Revenue code and procedure code do not match
- Description: Revenue code inconsistent with procedure code
- Appeal Strategy: Correct revenue code mapping and resubmit
- Required Evidence: Corrected claim with proper revenue code/procedure code alignment

### Timely Filing Denials

CARC 29 — The time limit for filing has expired
- Description: Claim submitted after payer timely filing deadline
- Appeal Strategy: Document original submission date; provide proof of timely filing or extenuating circumstances
- Required Evidence: Original claim submission confirmation, clearinghouse reports, proof of prior submission attempts

## RARC Codes — Common Remark Codes

RARC N30 — Patient ineligible for this service
- Context: Used with CARC 96; patient not eligible for specific service
- Appeal Action: Verify eligibility; obtain updated eligibility verification

RARC N56 — Procedure code billed is not correct
- Context: Used with CARC 4; incorrect procedure code
- Appeal Action: Review coding; submit corrected claim with proper CPT/HCPCS

RARC N115 — This decision was based on a National Coverage Determination (NCD)
- Context: Medicare denial based on NCD
- Appeal Action: Review specific NCD; document how patient meets NCD criteria

RARC N386 — This decision was based on a Local Coverage Determination (LCD)
- Context: Medicare denial based on LCD
- Appeal Action: Review specific LCD; document compliance with LCD criteria

RARC MA130 — Claim was denied based on a clinical edit
- Context: Clinical edit rule triggered denial
- Appeal Action: Review clinical edit logic; provide documentation overriding edit rationale

RARC N657 — This should be billed with the appropriate code for the service/supply provided
- Context: Incorrect code used for service
- Appeal Action: Review coding guidelines; resubmit with correct code
